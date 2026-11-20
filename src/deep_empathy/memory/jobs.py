"""Durable, coalescing background work. Cloud I/O never holds the user lock."""

import asyncio
import json
import logging

from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import Analysis, Psychology, Summary
from deep_empathy.memory.context import build_context
from deep_empathy.storage.repository import dump, now, uid
from deep_empathy.user_model.profile import persist_claims, prepare_claims, valid_citations

logger = logging.getLogger(__name__)


class ModelJobs:
    def __init__(self, repo, gateway, settings, locks, long_term=None):
        self.long_term = long_term
        self.repo, self.gateway, self.settings, self.locks = repo, gateway, settings, locks
        self.wakeup = asyncio.Event()
        self.execution = asyncio.Lock()
        self.runner = None

    async def start(self):
        if not self.settings.background_enabled:
            return
        # Recover interrupted work without violating the partial unique index.
        with self.repo.connect() as db:
            db.execute(
                "UPDATE model_jobs SET status='cancelled' WHERE status='running' AND EXISTS "
                "(SELECT 1 FROM model_jobs p WHERE p.user_id=model_jobs.user_id "
                "AND p.session_id=model_jobs.session_id AND p.status='pending')"
            )
            db.execute("UPDATE model_jobs SET status='pending' WHERE status='running'")
        self.runner = asyncio.create_task(self._loop(), name="deep-empathy-memory")

    async def close(self):
        if self.runner:
            self.runner.cancel()
            await asyncio.gather(self.runner, return_exceptions=True)
            self.runner = None

    def enqueue(self, db, owner, session_id, cutoff_id, revision, reasons):
        if not reasons or not self.settings.background_enabled:
            return None
        same = db.execute(
            "SELECT id,status FROM model_jobs WHERE user_id=? AND session_id=? "
            "AND cutoff_id=? AND revision=? AND status IN ('running','completed') LIMIT 1",
            (owner, session_id, cutoff_id, revision),
        ).fetchone()
        if same:
            return same["id"] if same["status"] == "running" else None
        pending = db.execute(
            "SELECT id FROM model_jobs WHERE user_id=? AND session_id=? AND status='pending'",
            (owner, session_id),
        ).fetchone()
        if pending:
            db.execute(
                "UPDATE model_jobs SET cutoff_id=?,revision=?,reasons=?,updated_at=? WHERE id=?",
                (cutoff_id, revision, dump(reasons), now(), pending["id"]),
            )
            return pending["id"]
        if db.execute("SELECT COUNT(*) FROM model_jobs WHERE status='pending'").fetchone()[0] >= 128:
            return None
        job_id, stamp = uid(), now()
        db.execute(
            "INSERT INTO model_jobs(id,user_id,session_id,cutoff_id,revision,status,reasons,created_at,updated_at) "
            "VALUES(?,?,?,?,?,'pending',?,?,?)",
            (job_id, owner, session_id, cutoff_id, revision, dump(reasons), stamp, stamp),
        )
        return job_id

    def valid(self, job):
        return bool(
            self.repo.rows(
                "SELECT j.id FROM model_jobs j JOIN users u ON j.user_id=u.id "
                "JOIN sessions s ON s.id=j.session_id WHERE j.id=? AND j.status='running' "
                "AND u.memory=1 AND u.memory_revision=j.revision AND s.mode='cloud'",
                (job["id"],),
            )
        )

    async def drain(self):
        """Wait for queued work; used by offline tests/tools, never by chat handlers."""
        while await self._step():
            pass

    async def _loop(self):
        while True:
            if await self._step():
                continue
            self.wakeup.clear()
            try:
                await asyncio.wait_for(self.wakeup.wait(), self.settings.background_poll_seconds)
            except asyncio.TimeoutError:
                pass

    async def _step(self):
        async with self.execution:
            rows = self.repo.rows("SELECT * FROM model_jobs WHERE status='pending' ORDER BY rowid LIMIT 1")
            if not rows:
                return False
            job = rows[0]
            try:
                await asyncio.wait_for(self._process(job), self.settings.background_timeout)
            except asyncio.CancelledError:
                raise  # Leave running jobs recoverable on restart.
            except Exception as error:
                code = (
                    error.code
                    if isinstance(error, AppError)
                    else (
                        "BACKGROUND_TIMEOUT"
                        if isinstance(error, asyncio.TimeoutError)
                        else "BACKGROUND_FAILED"
                    )
                )
                logger.warning("background_job_failed job_id=%s code=%s", job["id"], code)
                with self.repo.connect() as db:
                    db.execute(
                        "UPDATE model_jobs SET status='failed',error_code=?,updated_at=? "
                        "WHERE id=? AND status='running'",
                        (code, now(), job["id"]),
                    )
            return True

    async def _process(self, job):
        owner, session_id = job["user_id"], job["session_id"]
        async with self.locks.hold(owner):
            fresh = self.repo.rows("SELECT * FROM model_jobs WHERE id=? AND status='pending'", (job["id"],))
            if not fresh:
                return
            job.update(fresh[0])  # A newer foreground turn may have coalesced this job while we waited.
            with self.repo.connect() as db:
                db.execute(
                    "UPDATE model_jobs SET status='running',updated_at=? WHERE id=? AND status='pending'",
                    (now(), job["id"]),
                )
            if not self.valid(job):
                self._cancel(job)
                return
            current = self.repo.rows(
                "SELECT rowid AS seq,* FROM messages WHERE user_id=? AND id=?", (owner, job["cutoff_id"])
            )[0]
            context = build_context(
                self.repo,
                owner,
                session_id,
                current["content"],
                True,
                self.settings.max_context_chars,
                "cloud",
                cutoff=current["seq"],
            )
            context["history"] = [m for m in context["history"] if m["id"] != current["id"]]
            observations = context["history"] + context["related_observations"] + [current]
            existing = self.repo.profile(owner, include_inactive=True)
            older = self.repo.messages(owner, session_id, limit=40, cutoff=current["seq"])[:-12]
            summaries = self.repo.rows(
                "SELECT * FROM summaries WHERE user_id=? AND session_id=?", (owner, session_id)
            )
        # No lock is held while waiting for remote modeling.
        usage = []
        if self.long_term:
            await self.long_term.enrich(context, owner, current["content"])
            observations = context["history"] + context["related_observations"] + [current]
        analysis = await self.gateway.generate("analysis", {**context, "current": current}, Analysis, usage)
        citations = valid_citations(analysis.psychology.citations, observations)
        if not citations or len(citations) != len(analysis.psychology.citations):
            analysis.psychology = Psychology()
        prepared, discarded = prepare_claims(analysis.claims, observations, existing)
        if analysis.risk == "urgent":
            prepared = []
        analysis.claims = []
        if not self.valid(job):
            self._cancel(job)
            return
        summary, sources, summary_error = None, [], None
        previous_ids = json.loads(summaries[0]["source_ids"]) if summaries else []
        # Summaries run only when enough *new* older messages exist, inside this background job.
        new_older = [m for m in older if m["id"] not in previous_ids]
        if len(older) >= 18 and (not summaries or len(new_older) >= 10):
            bounded, chars = [], 0
            for m in reversed(older):
                if chars + len(m["content"]) > self.settings.max_context_chars:
                    break
                bounded.append(m)
                chars += len(m["content"])
            bounded.reverse()
            try:
                summary = await self.gateway.generate(
                    "summarization",
                    {"messages": bounded, "previous_summary": summaries[0]["text"] if summaries else ""},
                    Summary,
                    usage,
                )
            except AppError as error:
                summary_error = error.code  # Optional compression must not discard valid profile updates.
            if summary and (
                not summary.source_message_ids
                or not set(summary.source_message_ids) <= {m["id"] for m in bounded}
            ):
                summary = None
            if summary:
                # Track every supplied source so consolidation cadence is independent
                # of how many citation IDs the model happened to return.
                sources = list(dict.fromkeys(previous_ids + [m["id"] for m in bounded]))
        async with self.locks.hold(owner):
            if not self.valid(job):
                self._cancel(job)
                return
            with self.repo.connect() as db:
                persist_claims(db, owner, session_id, prepared)
                if self.long_term:
                    self.long_term.enqueue(owner, db)
                saved_turn = db.execute("SELECT trace,result FROM turns WHERE id=? AND user_id=?",
                                        (current["turn_id"], owner)).fetchone()
                if saved_turn:
                    trace = json.loads(saved_turn["trace"])
                    updates = []
                    for claim in prepared:
                        live = db.execute("SELECT id,layer,statement,status,version FROM claims WHERE id=? AND user_id=?",
                                          (claim["id"], owner)).fetchone()
                        if live:
                            updates.append({**dict(live), "change": "修正" if claim.get("supersedes_id")
                                            else "补充依据" if claim.get("merge_into") else "新增"})
                    trace["profile_updates"] = updates
                    db.execute("UPDATE turns SET trace=? WHERE id=? AND user_id=?",
                               (dump(trace), current["turn_id"], owner))
                db.execute(
                    "UPDATE turns SET analysis=? WHERE id=? AND user_id=?",
                    (dump(analysis.model_dump()), current["turn_id"], owner),
                )
                if summary:
                    db.execute(
                        "INSERT OR REPLACE INTO summaries VALUES(?,?,?,?,?)",
                        (session_id, owner, summary.text, dump(sources), now()),
                    )
                db.execute(
                    "UPDATE model_jobs SET status='completed',usage=?,updated_at=?,error_code=? WHERE id=?",
                    (dump({"calls": usage, "discarded_claims": discarded}), now(), summary_error, job["id"]),
                )

    def _cancel(self, job):
        with self.repo.connect() as db:
            db.execute(
                "UPDATE model_jobs SET status='cancelled',updated_at=? WHERE id=? AND status='running'",
                (now(), job["id"]),
            )
