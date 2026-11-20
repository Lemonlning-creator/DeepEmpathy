import asyncio
import json

import httpx
import pytest
from conftest import HEADERS, FakeCloud

from deep_empathy.api.app import create_app
from deep_empathy.config import Settings
from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import ChatRequest, Preparation
from deep_empathy.llm.gateway import CloudLLM
from deep_empathy.planning.routing import route


def setup(tmp_path, gateway=None):
    settings = Settings(
        database_path=str(tmp_path / "realtime.db"),
        demo_enabled=True,
        llm_base_url="https://example.test/v1",
        llm_api_key="test",
        llm_model="test",
    )
    app = create_app(settings, gateway=gateway or FakeCloud())
    owner, _ = app.state.repo.create_user()
    session = app.state.repo.create_session(owner, "cloud")["id"]
    return app, owner, session


@pytest.mark.asyncio
async def test_fast_is_one_call_deep_is_two_and_cache_is_zero(tmp_path):
    app, owner, sid = setup(tmp_path)
    service, gateway = app.state.service, app.state.service.gateway
    request = ChatRequest(content="今天有点累", request_id="fast-request")
    result = await service.send(owner, sid, request)
    assert result["processing"]["foreground_calls"] == 1
    assert [task for task, _ in gateway.calls] == ["respond"]
    assert app.state.repo.profile(owner) == []
    assert await service.send(owner, sid, request) == result
    assert len(gateway.calls) == 1
    deep = await service.send(
        owner, sid, ChatRequest(content="帮我分析一下这个两难", request_id="deep-request")
    )
    assert deep["processing"]["foreground_calls"] == 2
    assert [task for task, _ in gateway.calls] == ["respond", "prepare", "respond"]
    assert deep["processing"]["path"] == "deep"


def test_risk_cannot_be_forced_fast_and_deep_is_explicit():
    assert route("我不想活了", "fast")["path"] == "deep"
    assert route("想聊点什么", "deep")["path"] == "deep"
    assert route("帮我分析", "auto")["path"] == "deep"
    assert route("今天不错", "auto")["path"] == "fast"


@pytest.mark.asyncio
async def test_real_delta_arrives_before_completion_and_disconnect_saves_nothing(tmp_path):
    gate, entered = asyncio.Event(), asyncio.Event()

    class Slow(FakeCloud):
        async def stream(self, task, data, usage):
            yield "先听你说。"
            entered.set()
            await gate.wait()

    app, owner, sid = setup(tmp_path, Slow())
    stream = app.state.service.events(owner, sid, ChatRequest(content="有点累", request_id="stream-test"))
    assert (await anext(stream))["event"] == "meta"
    delta = await asyncio.wait_for(anext(stream), 0.5)
    assert delta == {"event": "delta", "data": {"text": "先听你说。"}}
    assert not app.state.repo.messages(owner, sid)
    await stream.aclose()  # Cancellation closes the waiting producer and releases the user lock.
    assert not app.state.repo.messages(owner, sid)
    assert not app.state.service.locks.entries


@pytest.mark.asyncio
async def test_coalescing_and_session_cutoff(tmp_path):
    app, owner, sid = setup(tmp_path)
    service = app.state.service
    for i in range(3):
        await service.send(owner, sid, ChatRequest(content=f"我喜欢第{i}种音乐", request_id=f"coalesce-{i}"))
    jobs = app.state.repo.rows("SELECT * FROM model_jobs WHERE status='pending'")
    assert len(jobs) == 1 and len(service.gateway.calls) == 3
    await service.jobs.drain()
    assert [task for task, _ in service.gateway.calls].count("analysis") == 1
    analysis = [data for task, data in service.gateway.calls if task == "analysis"][0]
    assert analysis["current"]["content"] == "我喜欢第2种音乐"
    assert all(m["id"] != analysis["current"]["id"] for m in analysis["history"])
    assert len(app.state.repo.profile(owner)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["memory_off", "delete_session", "delete_all", "correct"])
async def test_background_io_does_not_block_chat_and_stale_writes_are_discarded(tmp_path, mutation):
    class Blocked(FakeCloud):
        def __init__(self):
            super().__init__()
            self.started, self.release = asyncio.Event(), asyncio.Event()
            self.block = False

        async def generate(self, task, data, schema, usage, repair=True):
            if task == "analysis" and self.block:
                self.started.set()
                await self.release.wait()
            return await super().generate(task, data, schema, usage, repair=repair)

    gateway = Blocked()
    app, _, _ = setup(tmp_path, gateway)
    service, repo = app.state.service, app.state.repo
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=HEADERS
    ) as client:
        await client.post("/v1/bootstrap")
        sid = (await client.post("/v1/sessions", json={"mode": "cloud"})).json()["id"]
        path = f"/v1/sessions/{sid}/messages"
        assert (
            await client.post(path, json={"content": "我喜欢先被倾听", "request_id": "before-block"})
        ).status_code == 200
        await service.jobs.drain()
        claim = (await client.get("/v1/me/profile")).json()["claims"][0]
        gateway.block = True
        await client.post(path, json={"content": "我喜欢安静", "request_id": "during-block"})
        work = asyncio.create_task(service.jobs.drain())
        await asyncio.wait_for(gateway.started.wait(), 1)
        # Foreground completes while the background model is deliberately blocked.
        response = await asyncio.wait_for(
            client.post(path, json={"content": "今天聊点别的", "request_id": "next-fast"}), 0.5
        )
        assert response.status_code == 200
        if mutation == "memory_off":
            response = await client.patch("/v1/me/memory-settings", json={"enabled": False})
        elif mutation == "delete_session":
            response = await client.delete(f"/v1/sessions/{sid}")
        elif mutation == "delete_all":
            response = await client.delete("/v1/me/data")
        else:
            response = await client.patch(
                f"/v1/me/profile/claims/{claim['id']}",
                json={"action": "correct", "statement": "希望讨论办法"},
            )
        assert response.status_code == 200
        gateway.release.set()
        await asyncio.wait_for(work, 1)
        assert not repo.rows("SELECT * FROM model_jobs WHERE status IN ('running','pending')")
        if mutation in ("delete_all", "delete_session"):
            assert not repo.rows("SELECT * FROM claims")
        else:
            claims = (await client.get("/v1/me/profile")).json()["claims"]
            assert len(claims) == 1
            if mutation == "correct":
                assert claims[0]["statement"] == "希望讨论办法"
            else:
                assert len(claims[0]["evidence"]) == 1


@pytest.mark.asyncio
async def test_background_failure_does_not_fail_or_delete_successful_chat(tmp_path):
    gateway = FakeCloud()
    gateway.fail_task = "analysis"
    app, owner, sid = setup(tmp_path, gateway)
    result = await app.state.service.send(
        owner, sid, ChatRequest(content="我喜欢安静", request_id="bg-failure")
    )
    await app.state.service.jobs.drain()
    assert len(app.state.repo.messages(owner, sid)) == 2
    assert result["processing"]["foreground_calls"] == 1
    assert app.state.repo.rows("SELECT status FROM model_jobs")[0]["status"] == "failed"


def sse_event(value):
    return ("data: " + json.dumps(value, ensure_ascii=False) + "\n\n").encode()


@pytest.mark.asyncio
async def test_gateway_stream_forwards_content_only_and_reports_usage():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        chunks = [
            sse_event({"choices": [{"delta": {"reasoning_content": "PRIVATE"}}]}),
            sse_event({"choices": [{"delta": {"content": "听你说。"}}]}),
            sse_event({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            sse_event({"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}),
            b"data: [DONE]\n\n",
        ]
        return httpx.Response(200, content=b"".join(chunks))

    settings = Settings(llm_base_url="https://test/v1", llm_api_key="key", llm_model="model")
    gateway = CloudLLM(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    usage = []
    assert "".join([text async for text in gateway.stream("respond", {}, usage)]) == "听你说。"
    assert len(calls) == 1 and calls[0]["stream"] and "response_format" not in calls[0]
    assert usage[0]["prompt_tokens"] == 12
    await gateway.close()


@pytest.mark.asyncio
async def test_incomplete_upstream_stream_is_not_retried_after_exposing_text():
    calls = []

    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield sse_event({"choices": [{"delta": {"content": "部分回复"}}]})
            raise httpx.ReadError("disconnected")

    def handler(request):
        calls.append(1)
        return httpx.Response(200, stream=Broken())

    settings = Settings(llm_base_url="https://test/v1", llm_api_key="key", llm_model="model")
    gateway = CloudLLM(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    received = []
    with pytest.raises(AppError):
        async for text in gateway.stream("respond", {}, []):
            received.append(text)
    assert received == ["部分回复"] and len(calls) == 1
    await gateway.close()


@pytest.mark.asyncio
async def test_prepare_malformed_output_does_not_add_a_third_foreground_call():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "invalid"}}]})

    settings = Settings(llm_base_url="https://test/v1", llm_api_key="key", llm_model="model")
    gateway = CloudLLM(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(AppError):
        await gateway.generate("prepare", {}, Preparation, [], repair=False)
    assert len(calls) == 1
    await gateway.close()


def test_sse_endpoint_has_done_event_and_idempotent_replay(client, app):
    sid = client.post("/v1/sessions", json={"mode": "cloud"}).json()["id"]
    request = {"content": "今天有点累", "request_id": "sse-http-test"}
    path = f"/v1/sessions/{sid}/messages/stream"
    response = client.post(path, json=request)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    assert "event: delta" in response.text and "event: done" in response.text
    calls = len(app.state.service.gateway.calls)
    cached = client.post(path, json=request)
    assert "event: delta" not in cached.text and "event: done" in cached.text
    assert len(app.state.service.gateway.calls) == calls


@pytest.mark.asyncio
async def test_plain_chat_only_models_periodically_and_end_is_deduplicated(tmp_path):
    app, owner, sid = setup(tmp_path)
    for i in range(3):
        await app.state.service.send(
            owner, sid, ChatRequest(content="今天还不错", request_id=f"periodic-{i}")
        )
    assert not app.state.repo.rows("SELECT * FROM model_jobs")
    await app.state.service.send(owner, sid, ChatRequest(content="今天还不错", request_id="periodic-4"))
    assert len(app.state.repo.rows("SELECT * FROM model_jobs WHERE status='pending'")) == 1
    await app.state.service.jobs.drain()
    job = app.state.repo.rows("SELECT * FROM model_jobs")[0]
    with app.state.repo.connect() as db:
        assert (
            app.state.service.jobs.enqueue(
                db, owner, sid, job["cutoff_id"], job["revision"], ["session_ended"]
            )
            is None
        )


@pytest.mark.asyncio
async def test_background_restart_recovers_interrupted_job(tmp_path):
    app, owner, sid = setup(tmp_path)
    await app.state.service.send(owner, sid, ChatRequest(content="我喜欢安静", request_id="restart-test"))
    with app.state.repo.connect() as db:
        db.execute("UPDATE model_jobs SET status='running'")
    await app.state.service.jobs.start()
    await app.state.service.jobs.drain()
    await app.state.service.jobs.close()
    assert app.state.repo.rows("SELECT status FROM model_jobs")[0]["status"] == "completed"
    assert len(app.state.repo.profile(owner)) == 1


def test_schema_v1_is_migrated_without_losing_existing_identity(tmp_path):
    import hashlib
    import sqlite3

    from deep_empathy.storage.repository import Repository

    path = str(tmp_path / "v1.db")
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE users(id TEXT PRIMARY KEY,token_hash TEXT UNIQUE NOT NULL,memory INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO users VALUES(?,?,1,?)",
            ("owner", hashlib.sha256(b"old-token").hexdigest(), "2026-01-01"),
        )
        db.execute("PRAGMA user_version=1")
    repo = Repository(path)
    assert repo.authenticate("old-token")["id"] == "owner"
    assert repo.user("owner")["memory_revision"] == 0
    assert repo.rows("PRAGMA user_version")[0]["user_version"] == 4
