"""Durable Mem0 projection of authoritative, user-scoped evidence and semantic claims."""
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from deep_empathy.memory.mem0_store import Mem0Store
from deep_empathy.storage.repository import now, queue_memory_sync

logger = logging.getLogger(__name__)


def document(kind, source_id, text, **metadata):
    return {"id": f"{kind}:{source_id}", "kind": kind, "source_id": source_id,
            "text": text, "hash": hashlib.sha256(text.encode()).hexdigest(),
            "metadata": {"kind": kind, "source_id": source_id, **metadata}}


class LongTermMemory:
    def __init__(self, repo, settings, store=None):
        self.repo, self.settings = repo, settings
        self.enabled = settings.memory_provider == "mem0" and bool(
            settings.embedding_model and settings.embedding_base_url and settings.embedding_api_key
        )
        self.backend = hashlib.sha256(
            f"{Path(settings.memory_path).resolve()}:{settings.embedding_base_url}:{settings.embedding_model}:{settings.embedding_dims}".encode()
        ).hexdigest()
        self.store = store or (Mem0Store(settings) if self.enabled else None)
        self.runner = None
        self.execution = asyncio.Lock()
        self.wakeup = asyncio.Event()
        self.last_error = None

    def documents(self, owner):
        docs = {}
        # Semantic memory: evidence-gated, revisable claims, never hidden user-role settings.
        for c in self.repo.profile(owner):
            d = document("semantic", c["id"], f"[{c['layer']} / {c['status']}] {c['statement']}",
                         layer=c["layer"], status=c["status"], confidence=c["confidence"],
                         session_id=c["session_id"], occurred_at=c["created_at"])
            docs[d["id"]] = d
        # Episodic memory: actual user utterances with time, session and turn provenance.
        # Assistant prose/actions must never become fabricated personal experiences.
        rows = self.repo.rows(
            "SELECT m.*,a.content AS assistant_content FROM messages m JOIN sessions s ON s.id=m.session_id "
            "LEFT JOIN messages a ON a.turn_id=m.turn_id AND a.user_id=m.user_id AND a.role='assistant' "
            "JOIN turns t ON t.id=m.turn_id WHERE m.user_id=? AND s.user_id=? "
            "AND m.role='user' AND s.mode='cloud' AND COALESCE(json_extract(t.trace,'$.routing.urgent'),0)=0 "
            "AND COALESCE(json_extract(t.analysis,'$.risk'),'ordinary')<>'urgent'",
            (owner, owner),
        )
        for m in rows:
            d = document("episodic", m["id"], f"[{m['created_at']}] 用户原话：{m['content']}\n林予当时的回复（不是用户事实或动作完成证明）：{m['assistant_content'] or ''}",
                         session_id=m["session_id"], turn_id=m["turn_id"], occurred_at=m["created_at"])
            docs[d["id"]] = d
        return docs

    async def start(self):
        if not self.enabled:
            return
        with self.repo.connect() as db:
            db.execute("UPDATE memory_sync SET status='pending' WHERE status='running'")
            for row in db.execute("SELECT id FROM users WHERE memory=1").fetchall():
                queue_memory_sync(db, row["id"])
        self.runner = asyncio.create_task(self._loop(), name="mem0-index")

    async def close(self):
        if self.runner:
            self.runner.cancel()
            await asyncio.gather(self.runner, return_exceptions=True)
        if self.store:
            await self.store.close()

    def enqueue(self, owner, db=None):
        if not self.enabled:
            return
        if db is not None:
            queue_memory_sync(db, owner)
        else:
            with self.repo.connect() as connection:
                queue_memory_sync(connection, owner)
        self.wakeup.set()

    def revision(self, owner):
        rows = self.repo.rows("SELECT memory,memory_revision FROM users WHERE id=?", (owner,))
        return rows[0]["memory_revision"] if rows and rows[0]["memory"] else None

    async def _loop(self):
        while True:
            if await self.step():
                continue
            self.wakeup.clear()
            try:
                await asyncio.wait_for(self.wakeup.wait(), 1)
            except asyncio.TimeoutError:
                pass

    async def step(self):
        async with self.execution:
            return await self._step()

    async def _step(self):
        rows = self.repo.rows(
            "SELECT * FROM memory_sync WHERE status='pending' AND retry_after<=? ORDER BY updated_at LIMIT 1",
            (now(),),
        )
        if not rows:
            return False
        job = rows[0]
        owner, generation = job["user_id"], job["generation"]
        with self.repo.connect() as db:
            db.execute("UPDATE memory_sync SET status='running' WHERE user_id=? AND generation=?",
                       (owner, generation))
        try:
            revision = self.revision(owner)
            records = self.repo.rows("SELECT * FROM memory_index WHERE user_id=?", (owner,))
            epochs = self.repo.rows("SELECT revision,backend FROM memory_epochs WHERE user_id=?", (owner,))
            if (revision is None or not epochs or epochs[0]["revision"] != revision
                    or epochs[0]["backend"] != self.backend):
                await self.store.purge(owner)
                with self.repo.connect() as db:
                    db.execute("DELETE FROM memory_index WHERE user_id=?", (owner,))
                    db.execute("DELETE FROM memory_epochs WHERE user_id=?", (owner,))
                    if revision is not None:
                        db.execute("INSERT INTO memory_epochs VALUES(?,?,?)", (owner, revision, self.backend))
                records = []
            if revision is not None:
                docs = self.documents(owner)
                by_id = {r["document_id"]: r for r in records}
                for doc_id, old in by_id.items():
                    if doc_id not in docs or docs[doc_id]["hash"] != old["source_hash"]:
                        await self.store.delete(old["remote_id"])
                        with self.repo.connect() as db:
                            db.execute("DELETE FROM memory_index WHERE user_id=? AND document_id=?",
                                       (owner, doc_id))
                for doc in docs.values():
                    if self.revision(owner) != revision:
                        break  # A new generation will purge any in-flight old write.
                    old = by_id.get(doc["id"])
                    if old and old["source_hash"] == doc["hash"]:
                        continue
                    remote_id = await self.store.upsert(owner, doc, revision)
                    # Keep even stale IDs tracked so the next generation can physically purge them.
                    with self.repo.connect() as db:
                        db.execute("INSERT OR REPLACE INTO memory_index VALUES(?,?,?,?,?,?,?)",
                                   (owner, doc["id"], doc["kind"], doc["source_id"], doc["hash"], revision, remote_id))
            with self.repo.connect() as db:
                db.execute("UPDATE memory_sync SET status='completed',error_code=NULL,updated_at=? "
                           "WHERE user_id=? AND generation=?", (now(), owner, generation))
            self.last_error = None
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not expose provider exception text, request bodies, keys or memory content.
            self.last_error = "MEMORY_SYNC_FAILED"
            retry = (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()
            with self.repo.connect() as db:
                db.execute("UPDATE memory_sync SET status='pending',error_code=?,retry_after=?,updated_at=? "
                           "WHERE user_id=? AND generation=?",
                           (self.last_error, retry, now(), owner, generation))
            logger.warning("mem0_sync_failed code=%s", self.last_error)
        return True

    async def recall(self, owner, query):
        empty = {"episodic": [], "semantic": [], "status": "disabled"}
        if not self.enabled or self.revision(owner) is None:
            return empty
        revision = self.revision(owner)
        try:
            hits = await asyncio.wait_for(
                self.store.search(owner, query[:2000], revision, self.settings.memory_top_k),
                self.settings.memory_search_timeout,
            )
            if hits is None:
                return {**empty, "status": "indexing"}
            if self.revision(owner) != revision:
                return {**empty, "status": "invalidated"}
            docs = self.documents(owner)
            result = {**empty, "status": "mem0"}
            budget = self.settings.memory_context_chars
            seen_hits = set()
            for hit in hits:
                meta = hit.get("metadata") or {}
                doc = docs.get(meta.get("document_id"))
                if not doc or doc["id"] in seen_hits or meta.get("revision") != revision or meta.get("source_hash") != doc["hash"]:
                    continue
                # Return authoritative text, not arbitrary text returned by the vector store.
                if len(doc["text"]) > budget:
                    continue
                seen_hits.add(doc["id"])
                budget -= len(doc["text"])
                result[doc["kind"]].append({"text": doc["text"], **doc["metadata"]})
            return result
        except Exception:
            return {**empty, "status": "unavailable"}

    async def enrich(self, context, owner, query):
        result = await self.recall(owner, query)
        context["long_term_memory"] = result
        seen = {m["id"] for m in context["related_observations"] + context["history"]}
        for item in result["episodic"]:
            if item["source_id"] in seen:
                continue
            rows = self.repo.rows("SELECT * FROM messages WHERE id=? AND user_id=? AND role='user'",
                                  (item["source_id"], owner))
            if rows:
                context["related_observations"].append(rows[0])
                seen.add(item["source_id"])
        return result

    def status(self, owner):
        rows = self.repo.rows("SELECT status,error_code,updated_at FROM memory_sync WHERE user_id=?", (owner,))
        return {"provider": self.settings.memory_provider, "configured": self.enabled,
                "index": rows[0] if rows else None,
                "counts": self.repo.rows("SELECT kind,COUNT(*) AS count FROM memory_index WHERE user_id=? "
                                         "GROUP BY kind", (owner,))}
