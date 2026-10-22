
"""Prefer manually reviewed YouTube video IDs in dashboard display.

Read-only: preserves existing MySQL rows and editorial records.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def apply_approved_youtube_videos(rows, cursor, root):
    review_dir = Path(root) / "facts" / "youtube_video_reviews"
    approvals = {}

    for path in review_dir.glob("song_*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))

            if record.get("status") != "VIDEO_IDENTITY_REVIEW":
                continue
            if record.get("db_status") != "DB_STORED":
                continue
            if record.get("manually_checked_channel") is not True:
                continue
            if record.get("manually_checked_track_version") is not True:
                continue

            song_id = int(record["song_id"])
            video_id = record["video_id"]

            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                continue

            candidate = record.get("original_candidate") or {}
            if candidate.get("video_id") != video_id:
                continue
            if candidate.get("channel_id") != record.get("channel_id"):
                continue

            approved_at = datetime.fromisoformat(
                record["approved_at_utc"].replace("Z", "+00:00")
            )
            if approved_at.tzinfo is None:
                continue
            approved_at = approved_at.astimezone(timezone.utc)

            previous = approvals.get(song_id)
            if previous is None or approved_at > previous[0]:
                approvals[song_id] = (approved_at, video_id)

        except (OSError, ValueError, TypeError, KeyError):
            continue

    for row in rows:
        row["youtube_video_review_status"] = "UNREVIEWED"

        approved = approvals.get(int(row["song_id"]))
        if approved is None:
            continue

        approved_video_id = approved[1]

        cursor.execute(
            """
            SELECT
                youtube_video_id,
                youtube_title,
                youtube_channel,
                youtube_views,
                youtube_likes,
                youtube_comments,
                collected_at
            FROM youtube_stats
            WHERE song_id = %s
              AND youtube_video_id = %s
            ORDER BY youtube_id DESC
            LIMIT 1
            """,
            (row["song_id"], approved_video_id),
        )

        matching_video = cursor.fetchone()

        if matching_video is not None:
            row.update(matching_video)
            row["youtube_video_review_status"] = "APPROVED"

    return rows
