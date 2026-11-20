import asyncio
import json
import re
import time
from contextlib import asynccontextmanager

from deep_empathy.bookstore import agenda
from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import Preparation, Psychology
from deep_empathy.llm.demo import DemoLLM
from deep_empathy.memory.context import build_context
from deep_empathy.memory.jobs import ModelJobs
from deep_empathy.memory.long_term import LongTermMemory
from deep_empathy.planning.routing import modeling_reasons, route
from deep_empathy.prompts.templates import VERSION
from deep_empathy.storage.repository import dump, invalidate_memory, now, uid
from deep_empathy.user_model.profile import valid_citations


class UserLocks:
    """Serialize foreground turns and short memory commits; never background I/O."""

    def __init__(self):
        self.entries = {}

    @asynccontextmanager
    async def hold(self, owner):
        entry = self.entries.setdefault(owner, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if not entry[1]:
                self.entries.pop(owner, None)


class ChatService:
    def __init__(self, repo, gateway, settings, background_gateway=None, memory_store=None, weather=None):
        self.repo, self.gateway, self.settings = repo, gateway, settings
        self.weather = weather
        self.demo, self.locks = DemoLLM(), UserLocks()
        self.memory = LongTermMemory(repo, settings, memory_store)
        self.jobs = ModelJobs(repo, background_gateway or gateway, settings, self.locks, self.memory)

    async def send(self, owner, session_id, request):
        """Legacy JSON endpoint: same one/two-call pipeline, collected instead of streamed."""
        try:
            return await asyncio.wait_for(
                self._execute(owner, session_id, request), self.settings.turn_timeout
            )
        except asyncio.TimeoutError:
            raise AppError("TURN_TIMEOUT", "本轮处理超时，内容尚未保存，可以重试。", 504) from None

    async def events(self, owner, session_id, request):
        """Bounded queue provides backpressure; disconnect cancels the cloud request."""
        queue = asyncio.Queue(maxsize=32)

        async def produce():
            cancelled = False
            try:
                result = await asyncio.wait_for(
                    self._execute(owner, session_id, request, queue.put), self.settings.turn_timeout
                )
                await queue.put({"event": "done", "data": result})
            except asyncio.CancelledError:
                cancelled = True
                raise
            except Exception as error:
                if isinstance(error, asyncio.TimeoutError):
                    error = AppError("TURN_TIMEOUT", "本轮处理超时，未完整保存，可以重试。", 504)
                if not isinstance(error, AppError):
                    error = AppError("TURN_FAILED", "本轮未能完成，请重试。", 500)
                await queue.put({"event": "error", "data": {"code": error.code, "message": error.message}})
            finally:
                # Do not await a full queue when the consumer disconnected.
                if not cancelled:
                    await queue.put(None)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), 10)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": {}}
                    continue
                if event is None:
                    break
                yield event
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)

    async def _execute(self, owner, session_id, request, emit=None):
        started = time.monotonic()
        async with self.locks.hold(owner):
            repo, settings = self.repo, self.settings
            session = repo.session(owner, session_id)
            cached = repo.cached_turn(owner, request.request_id, session_id, request.content)
            if cached:
                return cached
            if not request.content.strip():
                raise AppError("EMPTY_MESSAGE", "先写下一点想说的话吧。")
            store = agenda()
            if request.interaction_mode == "in_person" and (
                not store["open"] or not request.scene or not request.scene.user_present
            ):
                raise AppError("STORE_UNAVAILABLE", "面对面交互需要营业时间到店；可以切换线上聊天。", 409)
            mode = session["mode"]
            if mode == "demo" and not settings.demo_enabled:
                raise AppError("DEMO_DISABLED", "演示模式未开启。", 403)
            if mode == "cloud" and not settings.configured:
                raise AppError("LLM_NOT_CONFIGURED", "尚未配置云端模型，请填写 .env 或开启演示。", 503)
            gateway = self.demo if mode == "demo" else self.gateway
            user = repo.user(owner)
            memory = bool(user["memory"]) and mode == "cloud"
            context = build_context(
                repo, owner, session_id, request.content, memory, min(settings.max_context_chars, 10000), mode
            )
            retrieval_started = time.monotonic()
            retrieval = await self.memory.enrich(context, owner, request.content) if memory else None
            retrieval_ms = round((time.monotonic() - retrieval_started) * 1000)
            turn_id = uid()
            current = {
                "id": uid(),
                "user_id": owner,
                "session_id": session_id,
                "turn_id": turn_id,
                "role": "user",
                "content": request.content,
                "created_at": now(),
            }
            routing = route(request.content, request.processing_mode)
            previous = repo.rows(
                "SELECT plan FROM turns WHERE user_id=? AND session_id=? ORDER BY rowid DESC LIMIT 2",
                (owner, session_id),
            )
            consecutive = 0
            for turn in previous:
                if not json.loads(turn["plan"]).get("ask_clarification"):
                    break
                consecutive += 1
            listen_only = bool(re.search(r"只想.*说|不需要建议|先听我|只想.*倾诉", request.content))
            allowed = consecutive < settings.defe.get("interaction", {}).get(
                "max_consecutive_clarifying_turns", 2
            )
            allowed = allowed and not listen_only
            data = {
                **context,
                "current": current,
                "persona": settings.persona,
                "clarification_allowed": allowed,
                "urgent": routing["urgent"],
            }
            weather = self.weather.context(request.weather_snapshot_id,
                                           request.weather_preview if settings.test_reset_on_reload else None) if self.weather else {
                "kind": "unknown", "status": "unavailable", "location": settings.weather_location,
                "label": "天气暂不可用", "is_preview": False,
            }
            data["interaction"] = {"mode": request.interaction_mode, "store": store, "weather": weather}
            if request.scene:
                data["bookstore_scene"] = request.scene.model_dump()
            if emit:
                await emit({"event": "meta", "data": {"turn_id": turn_id, "weather": weather, **routing}})
            usage, preparation = [], None
            if routing["path"] == "deep":
                # No schema repair here: a normal complex turn has exactly two model stages.
                preparation = await gateway.generate("prepare", data, Preparation, usage, repair=False)
                observations = context["history"] + context["related_observations"] + [current]
                psychology = preparation.analysis.psychology
                citations = valid_citations(psychology.citations, observations)
                if not citations or len(citations) != len(psychology.citations):
                    preparation.analysis.psychology = Psychology()
                preparation.analysis.claims = []
                preparation.plan.ask_clarification &= allowed
                preparation.plan.offer_advice &= (
                    preparation.analysis.support_preference == "advice" and not listen_only
                )
                if routing["urgent"] or preparation.analysis.risk == "urgent":
                    routing["urgent"] = True
                    preparation.analysis.risk = "urgent"
                    preparation.plan.goal = "优先眼前安全，鼓励联系现实可信的人或当地紧急服务"
                    preparation.plan.offer_advice = False
                data["preparation"] = preparation.model_dump()
            text, ttft = "", None
            async for delta in gateway.stream("respond", data, usage):
                text += delta
                if ttft is None:
                    ttft = round((time.monotonic() - started) * 1000)
                if len(text) > 4000:
                    raise AppError("REPLY_TOO_LONG", "回复过长，请重试。", 502)
                if emit:
                    await emit({"event": "delta", "data": {"text": delta}})
            if not text.strip():
                raise AppError("EMPTY_REPLY", "模型没有返回回复，请重试。", 502)
            # A style heuristic cannot retract an already streamed, complete reply.
            # Retain the prompt budget and record deviations without failing persistence.
            style_warnings = []
            if text.count("？") + text.count("?") > (1 if allowed else 0):
                style_warnings.append("question_budget_exceeded")
            assistant = {
                "id": uid(),
                "user_id": owner,
                "session_id": session_id,
                "turn_id": turn_id,
                "role": "assistant",
                "content": text,
                "created_at": now(),
            }
            calls = 2 if routing["path"] == "deep" else 1
            metrics = {
                "path": routing["path"],
                "foreground_calls": calls,
                "http_requests": sum(u.get("http_requests", 1) for u in usage) if mode == "cloud" else 0,
                "ttft_ms": ttft,
                "upstream_ttft_ms": next((u.get("upstream_ttft_ms") for u in usage if u.get("task") == "respond"), None),
                "memory_retrieval_ms": retrieval_ms,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
            }
            result = {
                "turn_id": turn_id,
                "messages": [current, assistant],
                "mode": mode,
                "processing": metrics,
            }
            trace = {
                "interaction": data["interaction"],
                "mode": "prompt_guided" if mode == "cloud" else "scripted_demo",
                "prompt_version": VERSION,
                "routing": routing,
                "usage": usage,
                **metrics,
                "profile_snapshot": context["profile"],
                "memory_retrieval": retrieval,
                "review": "in_generation_self_check_and_code",
                "style_warnings": style_warnings,
                "profile_updates": [],
                "latent_psychology": next((u.get("latent_psychology") for u in usage if u.get("task") == "respond"), None),
                "capability_usage": next((u.get("capability_usage", []) for u in usage if u.get("task") == "respond"), []),
            }
            if request.scene:
                trace["bookstore_scene"] = request.scene.model_dump()
            plan = (
                preparation.plan.model_dump()
                if preparation
                else {
                    "ask_clarification": bool(text.count("？") + text.count("?")),
                    "mode": "integrated_generation",
                }
            )
            with repo.connect() as db:
                for message in (current, assistant):
                    db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?,?)", tuple(message.values()))
                count = (
                    db.execute(
                        "SELECT COUNT(*) FROM turns WHERE user_id=? AND session_id=?", (owner, session_id)
                    ).fetchone()[0]
                    + 1
                )
                reasons = (
                    modeling_reasons(request.content, count, settings.background_interval) if memory else []
                )
                revision = user["memory_revision"]
                if memory and re.search(r"你理解错|你误会|不是这个意思|纠正一下|其实我", request.content):
                    invalidate_memory(db, owner)
                    revision += 1
                if routing["urgent"]:
                    reasons = []
                if memory and not routing["urgent"]:
                    self.memory.enqueue(owner, db)
                job_id = self.jobs.enqueue(db, owner, session_id, current["id"], revision, reasons)
                result["background_modeling"] = "queued" if job_id else "not_requested"
                trace["background_job_id"] = job_id
                db.execute(
                    "INSERT INTO turns VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        turn_id,
                        owner,
                        session_id,
                        request.request_id,
                        request.content,
                        dump(result),
                        dump(preparation.analysis.model_dump()) if preparation else "{}",
                        dump(plan),
                        dump(trace),
                        current["created_at"],
                    ),
                )
                db.execute(
                    "UPDATE sessions SET title=?,updated_at=? WHERE user_id=? AND id=?",
                    (
                        request.content[:24] if session["title"] == "新的心情记录" else session["title"],
                        now(),
                        owner,
                        session_id,
                    ),
                )
            if job_id:
                self.jobs.wakeup.set()
            return result
