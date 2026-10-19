"""Append-only human correction layer for previously reviewed YouTube Video IDs.

This module only reads review evidence and correction records. Corrections do
NOT update MySQL or the historical approval JSONs. No YouTube API is called.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
STATUS = "ACTIVE_VIDEO_CORRECTION"


def _err(message: str):
    from news.youtube_approval_lock import ApprovalIntegrityError
    raise ApprovalIntegrityError(message)


def _utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp missing")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return dt.astimezone(timezone.utc)


def _approved_evidence(review_dir: Path, song_id: int, filename: str, sha256: str, video_id: str) -> dict:
    """Require exact immutable reference to an existing historical approval."""
    filename = str(filename)
    if Path(filename).name != filename or not filename.startswith(f"song_{song_id}_") or not filename.endswith(".json"):
        raise ValueError("invalid target approval filename")
    path = review_dir / filename
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError("target approval file changed")
    record = json.loads(raw.decode("utf-8"))
    original = record.get("original_candidate") or {}
    if not (
        record.get("song_id") == song_id
        and record.get("status") == "VIDEO_IDENTITY_REVIEW"
        and record.get("db_status") == "DB_STORED"
        and record.get("manually_checked_channel") is True
        and record.get("manually_checked_track_version") is True
        and record.get("video_id") == video_id
        and original.get("video_id") == video_id
        and original.get("channel_id") == record.get("channel_id")
    ):
        raise ValueError("target is not a consistent completed human review")
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        raise ValueError("invalid approved video ID")
    _utc(record.get("approved_at_utc"))
    return record


def resolve_active_approval(review_dir: Path, song_id: int, original_latest: dict | None) -> dict | None:
    """Read a correction chain; fail closed on corruption/contradiction."""
    review_dir = Path(review_dir)
    correction_dir = review_dir.parent / "youtube_video_corrections"
    paths = list(correction_dir.glob(f"song_{int(song_id)}_*.json"))
    if not paths:
        return original_latest
    if original_latest is None:
        _err("정정 기록은 있지만 원래 승인 이력이 없어 작업 중단")
    active = dict(original_latest)
    corrections = []
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("song_id") != int(song_id):
                raise ValueError("correction song_id mismatch")
            if record.get("status") != STATUS or record.get("human_confirmed") is not True:
                raise ValueError("correction not confirmed")
            if record.get("publication_approved") is not False or record.get("db_modified") is not False:
                raise ValueError("correction claims unsupported publication or DB write")
            if not isinstance(record.get("reason"), str) or len(record["reason"].strip()) < 12:
                raise ValueError("missing correction reason")
            ts = _utc(record.get("recorded_at_utc"))
            vid = record.get("active_video_id")
            if not isinstance(vid, str) or not VIDEO_ID.fullmatch(vid):
                raise ValueError("invalid target video ID")
            reviewed = _approved_evidence(review_dir, int(song_id), record.get("source_approval_file"),
                                          record.get("source_approval_sha256"), vid)
            if record.get("active_channel_id") != reviewed.get("channel_id"):
                raise ValueError("channel ID differs from target approval")
            if record.get("active_channel") != reviewed.get("youtube_channel"):
                raise ValueError("channel name differs from target approval")
            if record.get("active_title") != reviewed.get("video_title"):
                raise ValueError("video title differs from target approval")
            if not isinstance(record.get("invalidated_video_ids"), list) or not all(
                isinstance(item, str) and VIDEO_ID.fullmatch(item) for item in record["invalidated_video_ids"]
            ):
                raise ValueError("invalid invalidation list")
            if vid in record["invalidated_video_ids"]:
                raise ValueError("active video also invalidated")
            corrections.append((ts, path.name, record))
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            _err(f"정정 기록 {path.name} 검증 실패: {exc}")
    corrections.sort(key=lambda item: (item[0], item[1]))
    previous_time = None
    for ts, filename, record in corrections:
        if previous_time is not None and ts <= previous_time:
            _err(f"정정 기록 시간 순서 충돌: {filename}")
        previous_time = ts
        if record.get("previous_active_video_id") != active["video_id"]:
            _err(f"정정 이력 연결 불일치: {filename}")
        active = {
            "video_id": record["active_video_id"],
            "channel": record["active_channel"],
            "title": record["active_title"],
            "source": "CORRECTION_AUDIT",
            "corrected_at_utc": record["recorded_at_utc"],
        }
    return active


def find_target_approval(review_dir: Path, song_id: int, video_id: str) -> tuple[Path, dict, str]:
    """Find exactly one unique complete review event for video_id; no writes."""
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError("YouTube Video ID must be exactly 11 characters")
    matches = []
    for path in Path(review_dir).glob(f"song_{int(song_id)}_*.json"):
        raw = path.read_bytes()
        rec = json.loads(raw.decode("utf-8"))
        if rec.get("video_id") == video_id:
            digest = hashlib.sha256(raw).hexdigest()
            _approved_evidence(Path(review_dir), int(song_id), path.name, digest, video_id)
            matches.append((path, rec, digest))
    if not matches:
        raise ValueError("요청한 Video ID의 기존 수동 승인 이력이 없습니다")
    # For repeated approval of identical video, verify it is the same channel.
    if len({rec.get("channel_id") for _, rec, _ in matches}) != 1:
        raise ValueError("기존 승인들의 Channel ID가 일치하지 않습니다")
    matches.sort(key=lambda item: _utc(item[1]["approved_at_utc"]), reverse=True)
    return matches[0]
