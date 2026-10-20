-- Explicit separate SQLite initialization only. Do not execute against MySQL.
CREATE TABLE users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 role TEXT NOT NULL DEFAULT 'READER' CHECK(role IN ('READER','JOURNALIST','EDITOR','ADMIN')),
 selection TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL
);
CREATE TABLE login_limits (key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_start INTEGER NOT NULL);
CREATE TABLE fact_reviews (
 id INTEGER PRIMARY KEY, week_end TEXT NOT NULL, reviewer_id INTEGER NOT NULL REFERENCES users(id),
 facts TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER fact_reviews_no_update BEFORE UPDATE ON fact_reviews BEGIN SELECT RAISE(ABORT,'immutable facts'); END;
CREATE TRIGGER fact_reviews_no_delete BEFORE DELETE ON fact_reviews BEGIN SELECT RAISE(ABORT,'immutable facts'); END;
CREATE TABLE articles (
 id INTEGER PRIMARY KEY, author_id INTEGER NOT NULL REFERENCES users(id), title TEXT NOT NULL,
 body TEXT NOT NULL, week_end TEXT NOT NULL, fact_ref TEXT NOT NULL, evidence TEXT NOT NULL,
 evidence_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 status TEXT NOT NULL CHECK(status IN ('DRAFT','PENDING_REVIEW','ON_HOLD','REVISED','APPROVED','WITHDRAWN')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE revisions (
 id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id), version INTEGER NOT NULL,
 actor_id INTEGER NOT NULL REFERENCES users(id), snapshot TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(article_id,version)
);
CREATE TABLE reviews (
 id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id), version INTEGER NOT NULL,
 reviewer_id INTEGER NOT NULL REFERENCES users(id), evidence_hash TEXT NOT NULL,
 checklist TEXT NOT NULL, comment TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('APPROVED','ON_HOLD')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE audit (
 id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), action TEXT NOT NULL,
 target TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER reviews_no_update BEFORE UPDATE ON reviews BEGIN SELECT RAISE(ABORT,'immutable review'); END;
CREATE TRIGGER reviews_no_delete BEFORE DELETE ON reviews BEGIN SELECT RAISE(ABORT,'immutable review'); END;
CREATE TRIGGER revisions_no_update BEFORE UPDATE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
CREATE TRIGGER revisions_no_delete BEFORE DELETE ON revisions BEGIN SELECT RAISE(ABORT,'immutable revision'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
