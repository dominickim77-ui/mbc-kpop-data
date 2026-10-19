"""MBC K-POP 데이터 저널리즘 · STEP 05-3

같은 지역의 2026-10-01·2026-10-08 주간 차트를 비교합니다.
원자료는 수정하지 않고, 결과 CSV와 Fact Sheet JSON을 새로 만듭니다.
기존 news/match_charts.py의 검증·매칭 함수를 재사용합니다.
"""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

# Keep both the historical file command and package/module imports working.
import sys
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from news.match_charts import build_matches, normalize, primary_artist, read_chart, positive_integer

ROOT = Path(__file__).resolve().parent.parent
SPOTIFY_OLD = ROOT / "data/charts/spotify/regional-global-weekly-2026-10-01.csv"
YOUTUBE_OLD = ROOT / "data/charts/youtube/youtube-charts-top-songs-global-weekly-20261001.csv"
OUTPUT_CSV = ROOT / "data/processed/weekly_changes_20261008.csv"
OUTPUT_FACTS = ROOT / "facts/weekly_comparison_fact_sheet_20261008.json"


def key_for(row, platform):
    if platform == "spotify":
        return (normalize(row["track_name"]), primary_artist(row["artist_names"]))
    return (normalize(row["Track Name"]), primary_artist(row["Artist Names"]))


def index_previous(rows, platform):
    """중복 키가 있으면 자동 비교하지 않습니다."""
    idx = {}
    duplicates = set()
    rank_key, metric_key = (("rank", "streams") if platform == "spotify"
                            else ("Rank", "Views"))
    for r in rows:
        rank = positive_integer(r[rank_key], platform + " previous rank")
        metric = positive_integer(r[metric_key], platform + " previous metric")
        if rank < 1:
            raise ValueError(f"{platform}: 순위는 1 이상이어야 합니다")
        key = key_for(r, platform)
        if key in idx:
            duplicates.add(key)
        else:
            idx[key] = (rank, metric)
    return idx, duplicates


def calculate():
    current_matches, match_facts = build_matches()
    spotify_old = read_chart(SPOTIFY_OLD,
                             {"rank", "track_name", "artist_names", "streams"}, 200)
    youtube_old = read_chart(YOUTUBE_OLD,
                             {"Rank", "Track Name", "Artist Names", "Views"}, 100)
    s_index, s_duplicates = index_previous(spotify_old, "spotify")
    y_index, y_duplicates = index_previous(youtube_old, "youtube")

    results = []
    for track in current_matches:
        s_key = (normalize(track["track_name"]), primary_artist(track["spotify_artists"]))
        y_key = (normalize(track["track_name"]), primary_artist(track["youtube_artists"]))
        s_last = s_index.get(s_key) if s_key not in s_duplicates else None
        y_last = y_index.get(y_key) if y_key not in y_duplicates else None
        s_now = track["spotify_weekly_streams"]
        y_now = track["youtube_weekly_views"]
        sr_now, yr_now = track["spotify_rank"], track["youtube_rank"]

        def pct(new, old):
            return round((new - old) / old * 100, 2) if old is not None and old > 0 else None

        results.append({
            "track_name": track["track_name"],
            "spotify_artists": track["spotify_artists"],
            "youtube_artists": track["youtube_artists"],
            "spotify_rank_20261001": s_last[0] if s_last else None,
            "spotify_rank_20261008": sr_now,
            "spotify_rank_movement_up": s_last[0] - sr_now if s_last else None,
            "spotify_streams_20261001": s_last[1] if s_last else None,
            "spotify_streams_20261008": s_now,
            "spotify_streams_change_pct": pct(s_now, s_last[1] if s_last else None),
            "youtube_rank_20261001": y_last[0] if y_last else None,
            "youtube_rank_20261008": yr_now,
            "youtube_rank_movement_up": y_last[0] - yr_now if y_last else None,
            "youtube_views_20261001": y_last[1] if y_last else None,
            "youtube_views_20261008": y_now,
            "youtube_views_change_pct": pct(y_now, y_last[1] if y_last else None),
            "spotify_previous_status": "matched" if s_last else "unmatched_or_ambiguous",
            "youtube_previous_status": "matched" if y_last else "unmatched_or_ambiguous",
            "song_version_review": "required",
            "kpop_category_review": "required",
        })

    by_title = {normalize(r["track_name"]): r for r in results}
    highlights = []
    for name in ["Hootie Frutti", "Animal", "SaWaDiKa"]:
        row = by_title.get(normalize(name))
        if row:
            highlights.append({k: row[k] for k in (
                "track_name", "spotify_rank_20261001", "spotify_rank_20261008",
                "spotify_rank_movement_up", "spotify_streams_change_pct",
                "youtube_rank_20261001", "youtube_rank_20261008",
                "youtube_rank_movement_up", "youtube_views_change_pct"
            )})

    facts = {
        "status": "DRAFT_NOT_FOR_PUBLICATION",
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
        "region": "Global",
        "week_previous": {"start": "2026-09-25", "end": "2026-10-01"},
        "week_current": {"start": "2026-10-02", "end": "2026-10-08"},
        "spotify_top_n": 200,
        "youtube_top_n": 100,
        "same_week_match_candidates": len(results),
        "both_top_100_candidates_current_week": match_facts["both_charts_top_100_candidates"],
        "both_weeks_matched_spotify": sum(r["spotify_previous_status"] == "matched" for r in results),
        "both_weeks_matched_youtube": sum(r["youtube_previous_status"] == "matched" for r in results),
        "kpop_related_examples_needing_human_review": highlights,
        "method": "Normalize song title and primary artist, match within each week; compute week-on-week changes only within the same platform",
        "source_files": [
            "data/charts/spotify/regional-global-weekly-2026-10-01.csv",
            "data/charts/spotify/regional-global-weekly-2026-10-08.csv",
            "data/charts/youtube/youtube-charts-top-songs-global-weekly-20261001.csv",
            "data/charts/youtube/youtube-charts-top-songs-global-weekly-20261008.csv",
        ],
        "review_required": True,
        "cautions": [
            "Songs matched by title and primary artist are candidates, not confirmed same recordings or versions.",
            "K-POP classification is not finalized; highlighted tracks are review examples only.",
            "The two platforms have unequal rank cutoffs (Spotify 200, YouTube 100).",
            "A missing previous-week match is unknown/unmatched, not zero streams or views.",
            "Spotify stream change and YouTube view change are calculated separately; do not divide one by the other.",
            "YouTube supplied Growth field is ignored; change percentages are recomputed from both weeks' raw Views.",
            "Rank movement is previous_rank minus current_rank; positive means moving toward #1.",
            "Relative week-on-week change does not establish causal explanations.",
        ],
    }
    return results, facts


def main():
    results, facts = calculate()
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FACTS.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    with OUTPUT_FACTS.open("w", encoding="utf-8") as f:
        json.dump(facts, f, ensure_ascii=False, indent=2)

    print(f"✅ 이번 주 공통 곡 매칭 후보: {facts['same_week_match_candidates']}곡")
    print(f"✅ 양쪽 모두 TOP 100 후보: {facts['both_top_100_candidates_current_week']}곡")
    print(f"✅ 전주 데이터 연결: Spotify {facts['both_weeks_matched_spotify']}곡 / YouTube {facts['both_weeks_matched_youtube']}곡")
    for r in facts["kpop_related_examples_needing_human_review"]:
        print(f"🎵 {r['track_name']}: Spotify {r['spotify_rank_20261001']}→{r['spotify_rank_20261008']}위, "
              f"YouTube {r['youtube_rank_20261001']}→{r['youtube_rank_20261008']}위, "
              f"YouTube 주간 조회수 변화 {r['youtube_views_change_pct']}%")
    print(f"📄 {OUTPUT_CSV.relative_to(ROOT)}")
    print(f"📄 {OUTPUT_FACTS.relative_to(ROOT)}")
    print("⚠️ 검수 전 초안: 동일 곡 버전 및 K-POP 분류 확인 필요")


def cli():
    import argparse
    parser = argparse.ArgumentParser(description='명시적 실행 시 기존 결과 파일을 생성하는 오프라인 도구')
    parser.parse_args()
    main()


if __name__ == '__main__':
    cli()
