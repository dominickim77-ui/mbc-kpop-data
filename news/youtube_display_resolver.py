
"""STEP 17B - Manually approved YouTube video display.

Read approved review records and show the matching video's
latest saved statistics. Never modify the database.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def apply_approved_youtube_videos(rows, cursor, root):
    """Show only the single currently ACTIVE reviewed Video ID (no writes)."""
    from news.youtube_approval_lock import latest_approved

    review_dir = Path(root) / "facts" / "youtube_video_reviews"
    for row in rows:
        row["youtube_video_review_status"] = "UNREVIEWED"
        active = latest_approved(review_dir, int(row["song_id"]))
        if active is None:
            continue
        cursor.execute(
            """SELECT youtube_video_id, youtube_title, youtube_channel,
                      youtube_views, youtube_likes, youtube_comments, collected_at
               FROM youtube_stats
               WHERE song_id = %s AND youtube_video_id = %s
               ORDER BY youtube_id DESC LIMIT 1""",
            (int(row["song_id"]), active["video_id"]),
        )
        matched = cursor.fetchone()
        if matched is None or matched["youtube_video_id"] != active["video_id"]:
            # Keep historical row for diagnosis, but never label it approved.
            row["youtube_video_review_status"] = "REVIEW_DATA_MISMATCH"
            continue
        row.update(matched)
        row["youtube_video_review_status"] = "APPROVED"
    return rows
