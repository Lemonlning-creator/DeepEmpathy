import json

from conftest import HEADERS, send, session
from fastapi.testclient import TestClient

from deep_empathy.api.app import create_app
from deep_empathy.config import Settings


def test_atomic_turn_evidence_and_idempotency(client, app):
    sid = session(client)
    first = send(client, sid)
    assert first.status_code == 200, first.text
    result = first.json()
    second = send(client, sid)
    assert second.json() == result
    assert len(client.get(f"/v1/sessions/{sid}/messages").json()["items"]) == 2
    claims = client.get("/v1/me/profile").json()["claims"]
    assert len(claims) == 1
    evidence = claims[0]["evidence"][0]
    assert evidence["quote"] == result["messages"][0]["content"][evidence["start"] : evidence["end"]]
    assert len(app.state.service.gateway.calls) == 2
    assert send(client, sid, text="different").status_code == 409


def test_cloud_failure_leaves_no_partial_turn(client, app):
    sid = session(client)
    app.state.service.gateway.fail_task = "generation"
    assert send(client, sid).status_code == 503
    assert not client.get(f"/v1/sessions/{sid}/messages").json()["items"]
    assert not client.get("/v1/me/profile").json()["claims"]
    app.state.service.gateway.fail_task = None
    assert send(client, sid).status_code == 200


def test_profile_correction_wins_and_retracted_wording_not_recreated(client, app):
    sid = session(client)
    send(client, sid)
    claim = client.get("/v1/me/profile").json()["claims"][0]
    result = client.patch(
        f"/v1/me/profile/claims/{claim['id']}", json={"action": "correct", "statement": "希望直接讨论办法"}
    )
    assert result.status_code == 200
    assert send(client, sid, key="request-0002").status_code == 200
    claims = client.get("/v1/me/profile").json()["claims"]
    assert len(claims) == 1 and claims[0]["statement"] == "希望直接讨论办法"
    assert claims[0]["status"] == "user_confirmed"
    assert claims[0]["evidence"][0]["source_type"] == "user_correction"
    analysis_data = [data for task, data in app.state.service.gateway.calls if task == "analysis"][-1]
    assert any(c["status"] == "retracted" for c in analysis_data["user_corrections"])


def test_memory_off_hides_cross_session_data_and_stops_profile_updates(client, app):
    sid = session(client)
    send(client, sid)
    client.patch("/v1/me/memory-settings", json={"enabled": False})
    second = session(client)
    assert send(client, second, text="今天想安静一下", key="request-0002").status_code == 200
    data = [data for task, data in app.state.service.gateway.calls if task == "analysis"][-1]
    assert data["profile"] == [] and data["related_observations"] == [] and data["user_corrections"] == []
    assert len(client.get("/v1/me/profile").json()["claims"]) == 1


def test_owner_isolation_for_history_profile_feedback_and_delete(client, app):
    sid = session(client)
    turn = send(client, sid).json()["turn_id"]
    claim = client.get("/v1/me/profile").json()["claims"][0]["id"]
    client.cookies.clear()
    stranger = client
    stranger.post("/v1/bootstrap")
    assert stranger.get(f"/v1/sessions/{sid}/messages").status_code == 404
    assert send(stranger, sid).status_code == 404
    assert stranger.delete(f"/v1/sessions/{sid}").status_code == 404
    assert stranger.patch(f"/v1/me/profile/claims/{claim}", json={"action": "confirm"}).status_code == 404
    assert stranger.post(f"/v1/turns/{turn}/feedback", json={"rating": "helpful"}).status_code == 404
    assert not stranger.get("/v1/me/profile").json()["claims"]


def test_delete_cascades_and_purges_derived_snapshots(client, app):
    sid = session(client)
    send(client, sid)
    second = session(client)
    send(client, second, key="request-0002")
    assert client.delete(f"/v1/sessions/{sid}").status_code == 200
    assert not client.get("/v1/me/profile").json()["claims"]
    rows = app.state.repo.rows("SELECT trace FROM turns")
    assert all(json.loads(r["trace"]) == {} for r in rows)
    assert client.delete("/v1/me/data").status_code == 200
    for table in ["users", "sessions", "messages", "claims", "evidence", "turns", "feedback", "summaries"]:
        assert app.state.repo.rows(f"SELECT * FROM {table}") == []
    assert client.get("/v1/sessions").status_code == 401


def test_demo_is_explicit_and_never_builds_profile(client, app):
    sid = session(client, "demo")
    result = send(client, sid, text="任意输入").json()
    assert result["mode"] == "demo"
    assert "没有调用大模型" in result["messages"][1]["content"]
    assert not client.get("/v1/me/profile").json()["claims"]
    assert not app.state.service.gateway.calls


def test_unconfigured_cloud_is_honest(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "empty.db")))
    with TestClient(app, headers=HEADERS) as client:
        client.post("/v1/bootstrap")
        sid = session(client)
        error = send(client, sid)
        assert error.status_code == 503 and error.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        assert not client.get(f"/v1/sessions/{sid}/messages").json()["items"]
        assert client.post("/v1/sessions", json={"mode": "demo"}).status_code == 403


def test_mutation_csrf_and_validation(client, app):
    assert (
        client.post(
            "/v1/sessions", json={"mode": "demo"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    raw = TestClient(app)
    assert raw.post("/v1/bootstrap").status_code == 403
    sid = session(client)
    assert send(client, sid, text=" ").status_code == 400
    result = send(client, sid, text="私密内容", key="bad")
    assert result.status_code == 422 and "私密内容" not in result.text


def test_feedback_upsert_and_pagination(client):
    sid = session(client)
    result = send(client, sid).json()
    tid = result["turn_id"]
    for rating in ["helpful", "missed"]:
        assert client.post(f"/v1/turns/{tid}/feedback", json={"rating": rating}).status_code == 200
    page = client.get(f"/v1/sessions/{sid}/messages?limit=1").json()
    assert page["items"][0]["feedback"] == "missed"
    earlier = client.get(f"/v1/sessions/{sid}/messages?before={page['next_cursor']}").json()
    assert earlier["items"][0]["role"] == "user"


def test_frontend_served_with_security_headers(client):
    page = client.get("/")
    assert page.status_code == 200 and "深予" in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200


def test_frontend_constant_element_references_exist(client):
    import re
    from html.parser import HTMLParser

    class Elements(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            self.ids.update(value for key, value in attrs if key == "id")

    parser = Elements()
    parser.feed(client.get("/").text)
    script = client.get("/static/app.js").text
    assert set(re.findall(r"\$\('([^']+)'\)", script)) <= parser.ids


def test_repeated_evidence_accumulates_without_duplicate_claims(client):
    first, second = session(client), session(client)
    assert send(client, first).status_code == 200
    assert send(client, first, key="request-0002").status_code == 200
    assert send(client, second, key="request-0003").status_code == 200
    claims = client.get("/v1/me/profile").json()["claims"]
    assert len(claims) == 1 and len(claims[0]["evidence"]) == 3
    assert claims[0]["status"] == "supported" and claims[0]["version"] == 3


def test_long_session_summary_is_grounded_and_deleted_with_session(client, app):
    from deep_empathy.domain.models import Summary

    original = app.state.service.gateway.generate

    async def summarize(task, data, schema, usage, repair=True):
        if task == "summarization":
            return Summary(text="用户希望先被倾听", source_message_ids=[data["messages"][0]["id"]])
        return await original(task, data, schema, usage)

    app.state.service.gateway.generate = summarize
    sid = session(client)
    for i in range(16):
        assert send(client, sid, key=f"summary-request-{i:04d}").status_code == 200
    summaries = app.state.repo.rows("SELECT * FROM summaries")
    assert len(summaries) == 1
    sources = json.loads(summaries[0]["source_ids"])
    assert app.state.repo.rows("SELECT id FROM messages WHERE id=?", (sources[0],))
    client.delete(f"/v1/sessions/{sid}")
    assert app.state.repo.rows("SELECT * FROM summaries") == []
