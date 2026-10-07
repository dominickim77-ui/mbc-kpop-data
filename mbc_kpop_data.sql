-- MBC K-POP 데이터 실습용 데이터베이스를 사용한다.
-- 아래 CREATE TABLE 명령들은 이 Schema 안에 테이블을 생성한다.
USE mbc_kpop_data;
/* create tables. */
CREATE TABLE tracks (
    song_id INT NOT NULL AUTO_INCREMENT,
    artist VARCHAR(255) NOT NULL,
    track VARCHAR(255) NOT NULL,
    PRIMARY KEY (song_id)
);

CREATE TABLE spotify_chart (
    spotify_id INT NOT NULL AUTO_INCREMENT,
    song_id INT NOT NULL,
    spotify_rank INT NOT NULL,
    spotify_streams BIGINT NOT NULL,
    chart_date DATE NOT NULL,
    collected_at DATETIME NOT NULL,
    PRIMARY KEY (spotify_id)
);

CREATE TABLE youtube_stats (
    youtube_id INT NOT NULL AUTO_INCREMENT,
    song_id INT NOT NULL,
    youtube_video_id VARCHAR(50) NOT NULL,
    youtube_title VARCHAR(500) NOT NULL,
    youtube_channel VARCHAR(255) NOT NULL,
    youtube_views BIGINT NOT NULL,
    youtube_likes BIGINT NOT NULL,
    youtube_comments BIGINT NOT NULL,
    collected_at DATETIME NOT NULL,
    PRIMARY KEY (youtube_id)
);


/* create foreign keys. */
ALTER TABLE spotify_chart
    ADD FOREIGN KEY (song_id)
    REFERENCES tracks (song_id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

ALTER TABLE youtube_stats
    ADD FOREIGN KEY (song_id)
    REFERENCES tracks (song_id)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT;

