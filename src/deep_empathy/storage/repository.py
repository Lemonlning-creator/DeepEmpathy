"""Small SQLite repository. Every query is scoped to an authenticated owner."""

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from deep_empathy.domain.errors import AppError


def uid():
    return uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(value):
    return json.dumps(value, ensure_ascii=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_sync(
 user_id TEXT PRIMARY KEY, generation INTEGER NOT NULL, status TEXT NOT NULL,
 error_code TEXT, retry_after TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memory_epochs(user_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,backend TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS memory_index(
 user_id TEXT NOT NULL, document_id TEXT NOT NULL, kind TEXT NOT NULL, source_id TEXT NOT NULL,
 source_hash TEXT NOT NULL, revision INTEGER NOT NULL, remote_id TEXT NOT NULL,
 PRIMARY KEY(user_id,document_id));
CREATE TABLE IF NOT EXISTS profile_initializations(
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 seed_id TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(user_id,seed_id));
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, memory INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 title TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 turn_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS message_session ON messages(user_id,session_id,created_at);
CREATE TABLE IF NOT EXISTS claims(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 layer TEXT NOT NULL, statement TEXT NOT NULL, status TEXT NOT NULL,
 explicit INTEGER NOT NULL, confidence REAL NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 supersedes_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
 message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
 quote TEXT NOT NULL, start INTEGER, end INTEGER, source_type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS turns(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 request_id TEXT NOT NULL, content TEXT NOT NULL, result TEXT NOT NULL,
 analysis TEXT NOT NULL, plan TEXT NOT NULL, trace TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(user_id,request_id));
CREATE TABLE IF NOT EXISTS feedback(
 turn_id TEXT PRIMARY KEY REFERENCES turns(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 rating TEXT NOT NULL, comment TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS summaries(
 session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 text TEXT NOT NULL, source_ids TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS model_jobs(
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 cutoff_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, status TEXT NOT NULL, reasons TEXT NOT NULL,
 error_code TEXT, usage TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_model_job ON model_jobs(user_id,session_id) WHERE status='pending';
CREATE TABLE IF NOT EXISTS scene_events(
 id INTEGER PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
 event_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
 description TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(user_id,event_id));
"""


def queue_memory_sync(db, owner):
    db.execute(
        "INSERT INTO memory_sync VALUES(?,1,'pending',NULL,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET generation=generation+1,status='pending',"
        "error_code=NULL,retry_after=excluded.retry_after,updated_at=excluded.updated_at",
        (owner, now(), now()),
    )


def invalidate_memory(db, owner):
    """User edits invalidate every snapshot that could contain older personal data."""
    db.execute("UPDATE users SET memory_revision=memory_revision+1 WHERE id=?", (owner,))
    queue_memory_sync(db, owner)
    db.execute(
        "UPDATE model_jobs SET status='cancelled',updated_at=? WHERE user_id=? "
        "AND status IN ('pending','running')",
        (now(), owner),
    )


class Repository:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            if "memory_revision" not in {r[1] for r in db.execute("PRAGMA table_info(users)")}:
                db.execute("ALTER TABLE users ADD COLUMN memory_revision INTEGER NOT NULL DEFAULT 0")
            if "backend" not in {r[1] for r in db.execute("PRAGMA table_info(memory_epochs)")}:
                db.execute("ALTER TABLE memory_epochs ADD COLUMN backend TEXT NOT NULL DEFAULT ''")
            db.execute("PRAGMA user_version=4")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def authenticate(self, token):
        if not token:
            return None
        values = self.rows(
            "SELECT id,memory FROM users WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)
        )
        return values[0] if values else None

    def create_user(self):
        token, user_id = secrets.token_urlsafe(32), uid()
        with self.connect() as db:
            db.execute(
                "INSERT INTO users(id,token_hash,memory,created_at) VALUES(?,?,1,?)",
                (user_id, hashlib.sha256(token.encode()).hexdigest(), now()),
            )
        return user_id, token

    def user(self, owner):
        users = self.rows("SELECT id,memory,memory_revision FROM users WHERE id=?", (owner,))
        if not users:
            raise AppError("UNAUTHORIZED", "请刷新页面重新建立本地身份。", 401)
        return users[0]

    def session(self, owner, session_id):
        rows = self.rows("SELECT * FROM sessions WHERE user_id=? AND id=?", (owner, session_id))
        if not rows:
            raise AppError("NOT_FOUND", "找不到这段对话。", 404)
        return rows[0]

    def create_session(self, owner, mode):
        session_id, stamp = uid(), now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                (session_id, owner, "新的心情记录", mode, stamp, stamp),
            )
        return self.session(owner, session_id)

    def messages(self, owner, session_id, limit=100, before=None, cutoff=None):
        self.session(owner, session_id)
        if cutoff:
            rows = self.rows(
                "SELECT * FROM messages WHERE user_id=? AND session_id=? "
                "AND rowid <= ? ORDER BY rowid DESC LIMIT ?",
                (owner, session_id, cutoff, limit),
            )
        elif before:
            boundary = self.rows(
                "SELECT rowid AS seq FROM messages WHERE user_id=? AND session_id=? AND id=?",
                (owner, session_id, before),
            )
            if not boundary:
                raise AppError("INVALID_CURSOR", "消息游标无效。")
            rows = self.rows(
                "SELECT * FROM messages WHERE user_id=? AND session_id=? AND rowid<? "
                "ORDER BY rowid DESC LIMIT ?",
                (owner, session_id, boundary[0]["seq"], limit),
            )
        else:
            rows = self.rows(
                "SELECT * FROM messages WHERE user_id=? AND session_id=? ORDER BY rowid DESC LIMIT ?",
                (owner, session_id, limit),
            )
        return list(reversed(rows))

    def profile(self, owner, include_inactive=False, limit=None):
        sql = "SELECT * FROM claims WHERE user_id=?"
        if not include_inactive:
            sql += " AND status NOT IN ('retracted','contradicted','superseded')"
        sql += " ORDER BY CASE WHEN status='user_confirmed' THEN 0 ELSE 1 END,updated_at DESC"
        claims = self.rows(sql + (" LIMIT ?" if limit else ""), (owner, limit) if limit else (owner,))
        for c in claims:
            c["evidence"] = self.rows(
                "SELECT e.*, m.created_at AS observed_at FROM evidence e "
                "LEFT JOIN messages m ON m.id=e.message_id "
                "WHERE e.user_id=? AND e.claim_id=?",
                (owner, c["id"]),
            )
        return claims

    def cached_turn(self, owner, request_id, session_id, content):
        turns = self.rows("SELECT * FROM turns WHERE user_id=? AND request_id=?", (owner, request_id))
        if not turns:
            return None
        turn = turns[0]
        if turn["session_id"] != session_id or turn["content"] != content:
            raise AppError("IDEMPOTENCY_CONFLICT", "该请求编号已用于其他内容，请重新发送。", 409)
        return json.loads(turn["result"])

    def delete_session(self, owner, session_id):
        self.session(owner, session_id)
        with self.connect() as db:
            invalidate_memory(db, owner)
            # Claims may gather evidence from several sessions. Remove any claim whose
            # evidence touches this session: conservative deletion avoids stale inference.
            db.execute(
                "DELETE FROM claims WHERE user_id=? AND id IN (SELECT e.claim_id FROM evidence e "
                "JOIN messages m ON m.id=e.message_id WHERE m.session_id=? AND m.user_id=?)",
                (owner, session_id, owner),
            )
            db.execute("DELETE FROM sessions WHERE user_id=? AND id=?", (owner, session_id))
            # Other turns may hold snapshots of the removed history. Purge derived
            # snapshots for this owner as well; final replies remain in their sessions.
            db.execute("UPDATE turns SET trace='{}',analysis='{}' WHERE user_id=?", (owner,))
