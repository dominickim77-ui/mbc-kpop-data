-- New EMPTY database bootstrap; select the target database explicitly.
-- Bootstrap for a NEW EMPTY, explicitly selected test database (MySQL 8.0).
-- No USE, CREATE DATABASE, IF NOT EXISTS, data inserts, or destructive statements.
-- Existing tables cause an error; do not run with --force.
-- Historical song_id values and approval JSONs are NOT restored by schema creation.
-- AUTO_INCREMENT counters are environment state and are intentionally omitted.

CREATE TABLE `tracks` (
  `song_id` int NOT NULL AUTO_INCREMENT,
  `artist` varchar(255) NOT NULL,
  `track` varchar(255) NOT NULL,
  PRIMARY KEY (`song_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `spotify_chart` (
  `spotify_id` int NOT NULL AUTO_INCREMENT,
  `song_id` int NOT NULL,
  `spotify_rank` int NOT NULL,
  `spotify_streams` bigint NOT NULL,
  `chart_date` date NOT NULL,
  `collected_at` datetime NOT NULL,
  PRIMARY KEY (`spotify_id`),
  UNIQUE KEY `uq_spotify_song_chart` (`song_id`,`chart_date`),
  CONSTRAINT `spotify_chart_ibfk_1` FOREIGN KEY (`song_id`) REFERENCES `tracks` (`song_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `youtube_stats` (
  `youtube_id` int NOT NULL AUTO_INCREMENT,
  `song_id` int NOT NULL,
  `youtube_video_id` varchar(50) NOT NULL,
  `youtube_title` varchar(500) NOT NULL,
  `youtube_channel` varchar(255) NOT NULL,
  `youtube_views` bigint NOT NULL,
  `youtube_likes` bigint NOT NULL,
  `youtube_comments` bigint NOT NULL,
  `collected_at` datetime NOT NULL,
  PRIMARY KEY (`youtube_id`),
  UNIQUE KEY `uq_youtube_video_collected` (`youtube_video_id`,`collected_at`),
  KEY `song_id` (`song_id`),
  CONSTRAINT `youtube_stats_ibfk_1` FOREIGN KEY (`song_id`) REFERENCES `tracks` (`song_id`) ON DELETE RESTRICT ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
