"""K-POP 주간 차트 4개 원본 CSV의 품질을 먼저 검증합니다."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "charts"
FILES = {
    "Spotify 10/01": DATA / "spotify" / "regional-global-weekly-2026-10-01.csv",
    "Spotify 10/08": DATA / "spotify" / "regional-global-weekly-2026-10-08.csv",
    "YouTube 10/01": DATA / "youtube" / "youtube-charts-top-songs-global-weekly-20261001.csv",
    "YouTube 10/08": DATA / "youtube" / "youtube-charts-top-songs-global-weekly-20261008.csv",
}


def inspect_csv(label: str, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        rows = list(reader)

    is_spotify = label.startswith("Spotify")
    needed = {"rank", "track_name", "artist_names", "streams"} if is_spotify else {
        "Rank", "Track Name", "Artist Names", "Views"
    }
    if not needed.issubset(columns):
        raise ValueError(f"{label}: 필수 열 누락: {sorted(needed - set(columns))}")
    if not rows:
        raise ValueError(f"{label}: 빈 CSV 파일")

    rank_col, count_col = ("rank", "streams") if is_spotify else ("Rank", "Views")
    ranks = []
    for row_no, row in enumerate(rows, start=2):
        try:
            rank = int(row[rank_col]); count = int(row[count_col])
        except (ValueError, TypeError):
            raise ValueError(f"{label}: {row_no}행의 순위나 수치가 정수가 아님") from None
        if rank < 1 or count < 0:
            raise ValueError(f"{label}: {row_no}행의 순위 또는 수치가 잘못됨")
        ranks.append(rank)
    if len(set(ranks)) != len(ranks):
        raise ValueError(f"{label}: 중복 순위 존재")

    unit = "streams/week" if is_spotify else "views/week"
    print(f"✅ {label}: {len(rows)}곡, {len(columns)}열, {unit}")


if __name__ == "__main__":
    for name, filepath in FILES.items():
        inspect_csv(name, filepath)
    print("✅ 네 파일의 기본 형식 검사 완료 (곡 매칭·기사 검수는 아직)")
