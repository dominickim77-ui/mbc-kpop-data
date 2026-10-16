"""MBC K-POP 데이터 저널리즘 수업 · STEP 02

Spotify/YouTube 2026-10-08 글로벌 주간 차트에서
'곡명 + 대표 아티스트'가 일치하는 *후보*를 찾습니다.

주의:
- 같은 기간 데이터라도 streams와 views를 서로 나누거나 빼면 안 됩니다.
- 곡/음원 버전의 동일성, K-POP 분류는 사람이 추가 검수해야 합니다.
- YouTube CSV의 Growth 열은 사용하지 않습니다.
"""

import csv
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPOTIFY_PATH = ROOT / "data" / "charts" / "spotify" / "regional-global-weekly-2026-10-08.csv"
YOUTUBE_PATH = ROOT / "data" / "charts" / "youtube" / "youtube-charts-top-songs-global-weekly-20261008.csv"
MATCHED_PATH = ROOT / "data" / "processed" / "spotify_youtube_match_candidates_20261008.csv"
FACTS_PATH = ROOT / "facts" / "matching_fact_sheet_20261008.json"


def normalize(text: str) -> str:
    """대소문자, 공백, 일부 문장부호 차이를 줄여 비교합니다."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def primary_artist(text: str) -> str:
    """Spotify 쉼표 / YouTube & 기호 앞의 대표 아티스트를 사용합니다."""
    return normalize(re.split(r"\s*(?:,| & )\s*", text, maxsplit=1)[0])


def read_chart(path: Path, required: set[str], expected_rows: int) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV 파일을 찾지 못했습니다: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name}: 필수 열 누락 {sorted(missing)}")
        rows = list(reader)
    if len(rows) != expected_rows:
        raise ValueError(f"{path.name}: {expected_rows}곡 예상, 실제 {len(rows)}곡")
    return rows


def positive_integer(value: str, label: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}은(는) 정수가 아닙니다: {value!r}") from None
    if number < 0:
        raise ValueError(f"{label}에 음수가 있습니다: {number}")
    return number


def build_matches() -> tuple[list[dict], dict]:
    spotify = read_chart(
        SPOTIFY_PATH, {"rank", "track_name", "artist_names", "streams", "uri"}, 200
    )
    youtube = read_chart(
        YOUTUBE_PATH, {"Rank", "Track Name", "Artist Names", "Views", "YouTube URL"}, 100
    )

    # 같은 이름/대표 아티스트를 갖는 데이터가 둘 이상이면 자동 매칭하지 않습니다.
    spotify_index = defaultdict(list)
    for row in spotify:
        rank = positive_integer(row["rank"], "Spotify rank")
        streams = positive_integer(row["streams"], "Spotify streams")
        if rank == 0:
            raise ValueError("Spotify 순위는 1 이상이어야 합니다")
        spotify_index[(normalize(row["track_name"]), primary_artist(row["artist_names"]))].append(
            (row, rank, streams)
        )

    matches = []
    ambiguous_keys = []
    for row in youtube:
        rank = positive_integer(row["Rank"], "YouTube Rank")
        views = positive_integer(row["Views"], "YouTube Views")
        if rank == 0:
            raise ValueError("YouTube 순위는 1 이상이어야 합니다")
        key = (normalize(row["Track Name"]), primary_artist(row["Artist Names"]))
        hits = spotify_index.get(key, [])
        if len(hits) > 1:
            ambiguous_keys.append({"title": row["Track Name"], "artist": row["Artist Names"]})
            continue
        if len(hits) != 1:
            continue
        track, s_rank, streams = hits[0]
        matches.append({
            "period_start": "2026-10-02",
            "period_end": "2026-10-08",
            "track_name": row["Track Name"],
            "spotify_artists": track["artist_names"],
            "youtube_artists": row["Artist Names"],
            "spotify_rank": s_rank,
            "youtube_rank": rank,
            "spotify_weekly_streams": streams,
            "youtube_weekly_views": views,
            "spotify_track_uri": track["uri"],
            "youtube_source_url": row["YouTube URL"],
            "match_method": "normalized_title_and_primary_artist",
            "review_status": "candidate_needs_version_and_artist_review",
        })

    matches.sort(key=lambda r: r["youtube_rank"])
    if len({(r["spotify_rank"], r["youtube_rank"]) for r in matches}) != len(matches):
        raise ValueError("중복 매칭 후보가 있습니다. 사람이 확인해야 합니다")

    facts = {
        "status": "DRAFT_NOT_FOR_PUBLICATION",
        "period_start": "2026-10-02",
        "period_end": "2026-10-08",
        "geography": "Global",
        "spotify_chart": "Weekly Top Songs Global, first 200 tracks",
        "youtube_chart": "Weekly Top Songs Global, first 100 tracks",
        "spotify_rows": len(spotify),
        "youtube_rows": len(youtube),
        "match_candidate_count": len(matches),
        "both_charts_top_100_candidates": sum(
            r["spotify_rank"] <= 100 and r["youtube_rank"] <= 100 for r in matches
        ),
        "ambiguous_matches_excluded": ambiguous_keys,
        "method": "Track title and primary artist are normalized and matched exactly",
        "review_required": True,
        "cautions": [
            "Matched entries are candidates, not verified identical song versions.",
            "Spotify streams and YouTube views must not be directly divided or compared as equal units.",
            "Global charts cover different numbers of ranked songs (Spotify 200, YouTube 100).",
            "K-POP artist classification has not been performed or verified.",
            "YouTube Growth CSV field is not used; calculate week-over-week changes from raw Views separately.",
        ],
        "source_files": [str(SPOTIFY_PATH.relative_to(ROOT)), str(YOUTUBE_PATH.relative_to(ROOT))],
    }
    return matches, facts


def main() -> None:
    matches, facts = build_matches()
    MATCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATCHED_PATH.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(matches[0]) if matches else [
            "period_start", "period_end", "track_name", "spotify_rank", "youtube_rank", "review_status"
        ])
        writer.writeheader()
        writer.writerows(matches)
    with FACTS_PATH.open("w", encoding="utf-8", newline="") as fp:
        json.dump(facts, fp, ensure_ascii=False, indent=2)

    print(f"✅ Spotify 10/08: {facts['spotify_rows']}곡")
    print(f"✅ YouTube 10/08: {facts['youtube_rows']}곡")
    print(f"✅ 곡명 + 대표 아티스트 일치 후보: {facts['match_candidate_count']}곡")
    print(f"✅ 양쪽 모두 TOP 100 후보: {facts['both_charts_top_100_candidates']}곡")
    print("\n🎵 검토할 K-POP 연계 후보 (자동 K-POP 분류 완료 아님)")
    for row in matches:
        if primary_artist(row["spotify_artists"]) in {"katseye", "lisa"}:
            print(f" - {row['track_name']}: Spotify {row['spotify_rank']}위 / YouTube {row['youtube_rank']}위")
    print(f"\n📄 매칭 CSV: {MATCHED_PATH.relative_to(ROOT)}")
    print(f"📄 Fact Sheet: {FACTS_PATH.relative_to(ROOT)}")
    print("⚠️ 곡 버전·K-POP 분류는 아직 사람 검수 필요")


if __name__ == "__main__":
    main()
