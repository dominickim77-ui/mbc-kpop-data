"""STEP 18: read-only latest manually approved YouTube identity lock.

Do not infer that a YouTube channel is official from its name.
A manual approval is a human attestation, not independent verification.
The most recent valid approved Video ID is locked against silent replacement.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")


class ApprovalIntegrityError(ValueError):
    """Do not proceed when the audit trail is contradictory or corrupt."""


def latest_approved(review_dir: Path, song_id: int) -> dict | None:
    """Return most recent DB_STORED human approval for a song, without writing.

    Relevant corrupt records fail closed, rather than silently unlocking an
    already-approved song. Incomplete DB writes also require reconciliation.
    """
    root = Path(review_dir)
    candidates = []
    for path in root.glob(f"song_{int(song_id)}_*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("song_id") != int(song_id):
                raise ValueError("song_id differs")
            if record.get("status") != "VIDEO_IDENTITY_REVIEW":
                raise ValueError("unexpected review status")
            if record.get("db_status") != "DB_STORED":
                raise ValueError("DB status requires reconciliation")
            if (record.get("manually_checked_channel") is not True
                    or record.get("manually_checked_track_version") is not True):
                raise ValueError("manual approval evidence incomplete")
            video_id = record.get("video_id")
            channel_id = record.get("channel_id")
            original = record.get("original_candidate")
            if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
                raise ValueError("invalid video ID")
            if not isinstance(original, dict) or original.get("video_id") != video_id or original.get("channel_id") != channel_id:
                raise ValueError("candidate reference mismatch")
            timestamp = datetime.fromisoformat(record["approved_at_utc"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("timestamp without time zone")
            candidates.append((timestamp.astimezone(timezone.utc), path.name, video_id,
                               record.get("youtube_channel") or "", record.get("video_title") or ""))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise ApprovalIntegrityError(f"검수 기록 {path.name}에 문제가 있어 승인 변경을 중단했습니다: {exc}") from None
    if not candidates:
        original_latest = None
    else:
        _, _, video_id, channel, title = max(candidates)
        original_latest = dict(video_id=video_id, channel=channel, title=title)
    # STEP18_CORRECTION: append-only human correction is the shared authority.
    from news.youtube_active_corrections import resolve_active_approval
    return resolve_active_approval(root, song_id, original_latest)
