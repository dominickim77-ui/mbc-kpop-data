"""CLI to append a human-reviewed ACTIVE-video correction (no DB writes)."""
from __future__ import annotations
import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from news.youtube_approval_lock import latest_approved, ApprovalIntegrityError
from news.youtube_active_corrections import find_target_approval


def verify_target_in_db(song_id: int, video_id: str, channel: str):
    from app import get_db_connection
    connection = get_db_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT youtube_video_id, youtube_channel FROM youtube_stats "
            "WHERE song_id=%s AND youtube_video_id=%s ORDER BY youtube_id DESC LIMIT 1",
            (song_id, video_id),
        )
        record = cursor.fetchone()
        if not record or record["youtube_video_id"] != video_id or record["youtube_channel"] != channel:
            raise ValueError("대상 Video ID/채널의 MySQL 기존 승인 행이 확인되지 않습니다")
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def main():
    parser = argparse.ArgumentParser(description="수동 승인 정정: 원본 JSON/MySQL 보존, 새 감사 이력만 추가")
    parser.add_argument("--song-id", type=int, required=True)
    parser.add_argument("--video-id", required=True, help="기존 수동 승인에 등장하는 공식 영상 ID")
    parser.add_argument("--expected-current", required=True, help="지금 잠긴 Video ID, 동시 변경 방지")
    parser.add_argument("--expected-channel", required=True, help="직접 확인한 채널명")
    parser.add_argument("--invalidate", action="append", default=[], help="정정 사유상 무효인 과거 Video ID. 반복 가능")
    parser.add_argument("--reason", required=True, help="최소 12자 사람의 정정 사유")
    parser.add_argument("--confirm", action="store_true", help="명시적 승인 후 append-only 정정 JSON 생성")
    args = parser.parse_args()
    if args.song_id < 1 or len(args.reason.strip()) < 12 or not args.expected_channel.strip():
        parser.error("song-id는 양수, 사유는 12자 이상, 채널명은 필수입니다")
    review_dir = ROOT / "facts" / "youtube_video_reviews"
    target_path, target, digest = find_target_approval(review_dir, args.song_id, args.video_id)
    active = latest_approved(review_dir, args.song_id)
    if not active or active["video_id"] != args.expected_current:
        raise ValueError("현재 ACTIVE 승인 상태가 예상과 다릅니다. 최신 이력 재검토 후 중단하세요")
    if target.get("youtube_channel") != args.expected_channel:
        raise ValueError("기존 승인 JSON의 채널명과 예상 공식 채널이 다릅니다")
    if args.video_id == active["video_id"]:
        raise ValueError("대상 영상이 이미 ACTIVE입니다. 중복 정정은 하지 않습니다")
    if args.video_id in args.invalidate or args.expected_current not in args.invalidate:
        raise ValueError("ACTIVE를 무효화하거나 현 ACTIVE 영상을 무효화 목록에서 빼면 안 됩니다")
    if len(args.invalidate) != len(set(args.invalidate)):
        raise ValueError("무효화 ID가 중복됐습니다")
    for vid in args.invalidate:
        find_target_approval(review_dir, args.song_id, vid)
    verify_target_in_db(args.song_id, args.video_id, args.expected_channel)
    print("현재 ACTIVE:", active["video_id"], active["channel"])
    print("정정할 ACTIVE:", args.video_id, target["youtube_channel"])
    print("무효화 대상:", ", ".join(args.invalidate))
    print("사유:", args.reason)
    if not args.confirm:
        print("✅ 사전 확인 완료 · 파일 변경 없음. 승인하려면 --confirm을 붙여 재실행하세요.")
        return 0
    now = datetime.now(timezone.utc)
    record = {
        "status": "ACTIVE_VIDEO_CORRECTION", "song_id": args.song_id,
        "recorded_at_utc": now.isoformat(), "human_confirmed": True,
        "previous_active_video_id": active["video_id"],
        "active_video_id": args.video_id,
        "active_channel": target["youtube_channel"],
        "active_channel_id": target["channel_id"],
        "active_title": target["video_title"],
        "source_approval_file": target_path.name,
        "source_approval_sha256": digest,
        "invalidated_video_ids": args.invalidate,
        "reason": args.reason.strip(),
        "db_modified": False, "publication_approved": False,
    }
    directory = ROOT / "facts" / "youtube_video_corrections"
    directory.mkdir(parents=True, exist_ok=True)
    name = f"song_{args.song_id}_{now:%Y%m%dT%H%M%S%fZ}_{uuid.uuid4().hex[:8]}.json"
    final = directory / name
    staging = directory / (name + ".tmp")
    try:
        with staging.open("x", encoding="utf-8") as out:
            json.dump(record, out, indent=2, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        staging.replace(final)
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    resolved = latest_approved(review_dir, args.song_id)
    if resolved is None or resolved["video_id"] != args.video_id:
        raise ValueError("정정 저장 후 일관성 검증이 실패했습니다. 재시도하지 말고 검수하세요")
    print("✅ 정정 기록 저장:", final.relative_to(ROOT))
    print("✅ ACTIVE 영상:", resolved["video_id"], resolved["channel"])
    print("✅ MySQL/기존 승인 JSON/기사 파일은 변경하지 않음")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, ApprovalIntegrityError, ImportError) as exc:
        raise SystemExit(f"❌ 정정 작업 중단: {exc}") from None
