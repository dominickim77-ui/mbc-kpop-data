-- Do not source this file directly. Use scripts/migrate_db_schema.py (dry-run default).
-- The guarded runner adds only absent equivalent indexes after a full preflight.
-- No row deletion/merging, index removal, ID reassignment, or production DDL.
ALTER TABLE spotify_chart ADD UNIQUE KEY uq_spotify_song_chart (song_id, chart_date);
ALTER TABLE youtube_stats ADD UNIQUE KEY uq_youtube_video_collected (youtube_video_id, collected_at);
