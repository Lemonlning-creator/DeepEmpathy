import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from deep_empathy.bookstore import agenda
from deep_empathy.config import Settings
from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import (
    ChatRequest,
    ClaimEdit,
    FeedbackRequest,
    MemorySearchRequest,
    MemorySettings,
    SceneEventsRequest,
    SessionRequest,
)
from deep_empathy.llm.demo import DEMO_INPUTS
from deep_empathy.llm.gateway import CloudLLM
from deep_empathy.orchestration.service import ChatService
from deep_empathy.storage.repository import Repository, invalidate_memory, now, uid
from deep_empathy.user_model.initial import initialize_profile
from deep_empathy.weather import ShopWeather

COOKIE = "deep_empathy_identity"
WEB = Path(__file__).resolve().parents[1] / "web"


def create_app(settings=None, gateway=None, memory_store=None):
    settings = settings or Settings.from_env()
    weather = ShopWeather(settings)
    repo = Repository(settings.database_path)
    cloud = gateway or CloudLLM(settings)
    background_cloud = gateway or CloudLLM(settings, background=True)
    service = ChatService(repo, cloud, settings, background_cloud, memory_store, weather)

    @asynccontextmanager
    async def lifespan(app):
        await service.memory.start()
        await service.jobs.start()
        try:
            yield
        finally:
            await weather.close()
            await service.jobs.close()
            await service.memory.close()
            if hasattr(cloud, "close"):
                await cloud.close()
            if background_cloud is not cloud and hasattr(background_cloud, "close"):
                await background_cloud.close()

    app = FastAPI(title="DeepEmpathy", version="0.1.0", lifespan=lifespan)
    app.state.repo, app.state.service, app.state.settings = repo, service, settings

    app.state.weather = weather

    @app.get("/v1/bookstore/weather")
    async def bookstore_weather():
        return await weather.current()

    @app.get("/v1/bookstore/agenda")
    async def bookstore_agenda():
        return agenda()

    @app.middleware("http")
    async def security_headers(request, call_next):
        # Cookie identity is local-device scoped. Disallow cross-origin mutations.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin != expected):
                return JSONResponse(
                    {"error": {"code": "ORIGIN_REJECTED", "message": "不允许跨站请求。"}}, 403
                )
            if request.headers.get("x-deep-empathy") != "1":
                return JSONResponse(
                    {"error": {"code": "CLIENT_HEADER_REQUIRED", "message": "缺少客户端校验头。"}}, 403
                )
        response = await call_next(request)
        if request.url.path == "/bookstore" or request.url.path.startswith("/static/bookstore"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/v1"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def app_error(request, error):
        return JSONResponse({"error": {"code": error.code, "message": error.message}}, error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # FastAPI's default body includes user input; avoid copying sensitive text to errors.
        return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": "输入格式或长度不正确。"}}, 422)

    def owner(request: Request):
        user = repo.authenticate(request.cookies.get(COOKIE))
        if not user:
            raise AppError("UNAUTHORIZED", "请刷新页面重新建立本地身份。", 401)
        return user["id"]

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "prompt_guided"}

    @app.post("/v1/bootstrap")
    async def bootstrap(request: Request):
        user = repo.authenticate(request.cookies.get(COOKIE))
        token = None
        if user and settings.test_reset_on_reload and request.query_params.get("reset_for_test") == "1":
            old_owner = user["id"]
            async with service.locks.hold(old_owner):
                with repo.connect() as db:
                    # Keep a durable purge task after cascading away all personal records.
                    service.memory.enqueue(old_owner, db)
                    db.execute("DELETE FROM users WHERE id=?", (old_owner,))
            user = None
        if not user:
            user_id, token = repo.create_user()
            user = repo.user(user_id)
        async with service.locks.hold(user["id"]):
            initialize_profile(repo, user["id"], settings.initial_profile)
            service.memory.enqueue(user["id"])
        response = JSONResponse(
            {
                "memory_enabled": bool(user["memory"]),
                "cloud_configured": settings.configured,
                "demo_enabled": settings.demo_enabled,
                "test_reset_on_reload": settings.test_reset_on_reload,
                "demo_inputs": DEMO_INPUTS,
            }
        )
        if token:
            response.set_cookie(
                COOKIE,
                token,
                httponly=True,
                samesite="strict",
                secure=settings.cookie_secure,
                max_age=365 * 24 * 3600,
            )
        return response

    @app.get("/v1/sessions")
    async def sessions(user=Depends(owner)):
        return repo.rows("SELECT * FROM sessions WHERE user_id=? ORDER BY updated_at DESC", (user,))

    @app.post("/v1/sessions")
    async def create_session(body: SessionRequest, user=Depends(owner)):
        if body.mode == "demo" and not settings.demo_enabled:
            raise AppError("DEMO_DISABLED", "请在服务端显式开启 DEMO_ENABLED。", 403)
        async with service.locks.hold(user):
            return repo.create_session(user, body.mode)

    @app.get("/v1/sessions/{session_id}/messages")
    async def messages(session_id: str, before: str | None = None, limit: int = 60, user=Depends(owner)):
        if not 1 <= limit <= 100:
            raise AppError("INVALID_LIMIT", "分页大小应为 1~100。")
        items = repo.messages(user, session_id, limit, before)
        feedback = {
            x["turn_id"]: x["rating"]
            for x in repo.rows(
                "SELECT f.* FROM feedback f JOIN turns t ON f.turn_id=t.id WHERE f.user_id=? AND t.session_id=?",
                (user, session_id),
            )
        }
        for item in items:
            item["feedback"] = feedback.get(item["turn_id"])
        return {"items": items, "next_cursor": items[0]["id"] if len(items) == limit else None}

    @app.post("/v1/sessions/{session_id}/messages")
    async def send(session_id: str, body: ChatRequest, user=Depends(owner)):
        return await service.send(user, session_id, body)

    @app.post("/v1/sessions/{session_id}/messages/stream")
    async def stream(session_id: str, body: ChatRequest, user=Depends(owner)):
        session = repo.session(user, session_id)
        if session["mode"] == "cloud" and not settings.configured:
            raise AppError("LLM_NOT_CONFIGURED", "尚未配置云端模型，请填写 .env 或开启演示。", 503)

        async def events():
            async for event in service.events(user, session_id, body):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post("/v1/sessions/{session_id}/consolidate")
    async def consolidate(session_id: str, user=Depends(owner)):
        async with service.locks.hold(user):
            session = repo.session(user, session_id)
            account = repo.user(user)
            if not account["memory"] or session["mode"] != "cloud":
                return {"queued": False}
            messages = repo.rows(
                "SELECT id FROM messages WHERE user_id=? AND session_id=? "
                "AND role='user' ORDER BY rowid DESC LIMIT 1",
                (user, session_id),
            )
            if not messages:
                return {"queued": False}
            with repo.connect() as db:
                job_id = service.jobs.enqueue(
                    db, user, session_id, messages[0]["id"], account["memory_revision"], ["session_ended"]
                )
            service.jobs.wakeup.set()
        return {"queued": bool(job_id)}

    @app.delete("/v1/sessions/{session_id}")
    async def delete_session(session_id: str, user=Depends(owner)):
        async with service.locks.hold(user):
            repo.delete_session(user, session_id)
        return {"deleted": True}

    @app.get("/v1/me/profile")
    async def profile(user=Depends(owner)):
        return {
            "claims": repo.profile(user),
            "memory_enabled": bool(repo.user(user)["memory"]),
            "note": "这些是可修正的理解，不是心理诊断。置信度是工程评分。",
        }

    @app.get("/v1/sessions/{session_id}/insights")
    async def insights(session_id: str, user=Depends(owner)):
        session = repo.session(user, session_id)
        rows = repo.rows(
            "SELECT analysis,created_at FROM turns WHERE user_id=? AND session_id=? "
            "AND analysis<>'{}' ORDER BY rowid DESC LIMIT 1",
            (user, session_id),
        )
        jobs = repo.rows(
            "SELECT status,updated_at FROM model_jobs WHERE user_id=? AND session_id=? "
            "ORDER BY rowid DESC LIMIT 1",
            (user, session_id),
        )
        latest = repo.rows(
            "SELECT id,analysis,trace FROM turns WHERE user_id=? AND session_id=? ORDER BY rowid DESC LIMIT 1",
            (user, session_id),
        )
        current_turn = None
        if latest and session["mode"] == "cloud":
            turn = latest[0]
            trace = json.loads(turn["trace"])
            turn_jobs = repo.rows("SELECT status FROM model_jobs WHERE id=? AND user_id=?",
                                  (trace.get("background_job_id"), user))
            current_turn = {
                "id": turn["id"],
                "modeling_status": turn_jobs[0]["status"] if turn_jobs else "not_requested",
                "psychology": json.loads(turn["analysis"]).get("psychology"),
                "capabilities": trace.get("capability_usage", []),
                "latent_psychology": trace.get("latent_psychology"),
                "profile_updates": trace.get("profile_updates", []),
            }
        return {
            "claims": repo.profile(user, limit=64) if session["mode"] == "cloud" else [],
            "current_turn": current_turn,
            "psychology": json.loads(rows[0]["analysis"]).get("psychology")
            if rows and session["mode"] == "cloud"
            else None,
            "observed_at": rows[0]["created_at"] if rows else None,
            "modeling_status": jobs[0]["status"] if jobs else "idle",
            "memory_enabled": bool(repo.user(user)["memory"]),
            "mode": session["mode"],
        }

    @app.post("/v1/sessions/{session_id}/scene-events")
    async def scene_events(session_id: str, body: SceneEventsRequest, user=Depends(owner)):
        async with service.locks.hold(user):
            repo.session(user, session_id)
            with repo.connect() as db:
                for event in body.events:
                    db.execute(
                        "INSERT OR IGNORE INTO scene_events(user_id,session_id,event_id,action,actor,description,created_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (user, session_id, event.id, event.action, event.actor, event.description, now()),
                    )
        return {"accepted": True}

    @app.patch("/v1/me/profile/claims/{claim_id}")
    async def edit_claim(claim_id: str, body: ClaimEdit, user=Depends(owner)):
        if body.action == "correct" and not body.statement.strip():
            raise AppError("EMPTY_CORRECTION", "请填写你的纠正内容。")
        async with service.locks.hold(user):
            rows = repo.rows("SELECT * FROM claims WHERE user_id=? AND id=?", (user, claim_id))
            if not rows or rows[0]["status"] in ("retracted", "contradicted"):
                raise AppError("NOT_FOUND", "这项理解已撤回或不存在。", 404)
            claim, stamp = rows[0], now()
            with repo.connect() as db:
                invalidate_memory(db, user)
                status = "user_confirmed" if body.action == "confirm" else "retracted"
                db.execute(
                    "UPDATE claims SET status=?,version=version+1,updated_at=? WHERE user_id=? AND id=?",
                    (status, stamp, user, claim_id),
                )
                if body.action == "correct":
                    new_id = uid()
                    db.execute(
                        "INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            new_id,
                            user,
                            claim["session_id"],
                            claim["layer"],
                            body.statement.strip(),
                            "user_confirmed",
                            1,
                            1.0,
                            1,
                            claim_id,
                            stamp,
                            stamp,
                        ),
                    )
                    db.execute(
                        "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)",
                        (uid(), user, new_id, None, body.statement.strip(), None, None, "user_correction"),
                    )
                # Historical traces must not continue exposing a superseded profile.
                db.execute("UPDATE turns SET trace='{}' WHERE user_id=?", (user,))
        return {"updated": True}

    @app.get("/v1/me/memory-status")
    async def memory_status(user=Depends(owner)):
        return service.memory.status(user)

    @app.post("/v1/me/memories/search")
    async def memory_search(body: MemorySearchRequest, user=Depends(owner)):
        return await service.memory.recall(user, body.query)

    @app.patch("/v1/me/memory-settings")
    async def memory_settings(body: MemorySettings, user=Depends(owner)):
        async with service.locks.hold(user):
            with repo.connect() as db:
                invalidate_memory(db, user)
                db.execute("UPDATE users SET memory=? WHERE id=?", (int(body.enabled), user))
        return {"enabled": body.enabled}

    @app.post("/v1/turns/{turn_id}/feedback")
    async def feedback(turn_id: str, body: FeedbackRequest, user=Depends(owner)):
        async with service.locks.hold(user):
            rows = repo.rows("SELECT id FROM turns WHERE user_id=? AND id=?", (user, turn_id))
            if not rows:
                raise AppError("NOT_FOUND", "找不到这条回复。", 404)
            with repo.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO feedback VALUES(?,?,?,?,?)",
                    (turn_id, user, body.rating, body.comment, now()),
                )
        return {"saved": True}

    @app.delete("/v1/me/data")
    async def delete_data(user=Depends(owner)):
        async with service.locks.hold(user):
            with repo.connect() as db:
                service.memory.enqueue(user, db)
                db.execute("DELETE FROM users WHERE id=?", (user,))
        response = JSONResponse({"deleted": True})
        response.delete_cookie(COOKIE)
        return response

    @app.get("/")
    async def index():
        return FileResponse(WEB / "index.html")

    @app.get("/bookstore")
    async def bookstore():
        return FileResponse(WEB / "bookstore.html")

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
