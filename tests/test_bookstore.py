import json

from conftest import session
from fastapi.testclient import TestClient


def test_bookstore_and_local_3d_assets_are_served(client):
    response = client.get("/bookstore")
    assert response.status_code == 200 and "慢屿书屋" in response.text
    for path in [
        "bookstore.js",
        "bookstore-state.mjs",
        "bookstore-scene.js",
        "vendor/three/three.module.js",
        "vendor/three/three.core.js",
        "vendor/three/OrbitControls.js",
    ]:
        asset = client.get("/static/" + path)
        assert asset.status_code == 200
    assert "from './three.module.js'" in client.get("/static/vendor/three/OrbitControls.js").text


def test_scene_events_are_owned_deduplicated_and_never_model_calls(client, app):
    sid = session(client)
    events = {
        "events": [{"id": "entry-event", "action": "enter", "actor": "user", "description": "朋友进店"}]
    }
    path = f"/v1/sessions/{sid}/scene-events"
    assert client.post(path, json=events).status_code == 200
    assert client.post(path, json=events).status_code == 200
    assert len(app.state.repo.rows("SELECT * FROM scene_events")) == 1
    assert not app.state.service.gateway.calls
    stranger = TestClient(app, headers={"X-Deep-Empathy": "1"})
    stranger.post("/v1/bootstrap")
    assert stranger.post(path, json=events).status_code == 404
    assert stranger.get(f"/v1/sessions/{sid}/insights").status_code == 404
    assert client.delete(f"/v1/sessions/{sid}").status_code == 200
    assert not app.state.repo.rows("SELECT * FROM scene_events")


def test_chat_receives_validated_scene_without_additional_foreground_calls(client, app):
    sid = session(client)
    scene = {
        "scene_id": "bookstore",
        "user_present": True,
        "boss_pose": "standing",
        "user_pose": "sitting",
        "reading_title": "把日子过慢一点",
        "recent_events": [],
    }
    result = client.post(
        f"/v1/sessions/{sid}/messages",
        json={"content": "今天过得不错", "request_id": "bookstore-chat", "scene": scene},
    )
    assert result.status_code == 200
    assert result.json()["processing"]["foreground_calls"] == 1
    calls = app.state.service.gateway.calls
    assert len(calls) == 1 and calls[0][1]["bookstore_scene"]["user_pose"] == "sitting"
    trace = json.loads(app.state.repo.rows("SELECT trace FROM turns")[0]["trace"])
    assert trace["bookstore_scene"]["reading_title"] == "把日子过慢一点"
    bad = {**scene, "boss_pose": "flying"}
    assert (
        client.post(
            f"/v1/sessions/{sid}/messages",
            json={"content": "你好", "request_id": "bad-world-state", "scene": bad},
        ).status_code
        == 422
    )


def test_insights_show_real_background_changes(client, app):
    sid = session(client)
    response = client.get(f"/v1/sessions/{sid}/insights").json()
    assert response["claims"] == [] and response["psychology"] is None
    client.post(
        f"/v1/sessions/{sid}/messages", json={"content": "我喜欢先被倾听", "request_id": "insight-update"}
    )
    client.portal.call(app.state.service.jobs.drain)
    response = client.get(f"/v1/sessions/{sid}/insights").json()
    assert len(response["claims"]) == 1 and response["psychology"]["interpretation"]
    demo = session(client, "demo")
    response = client.get(f"/v1/sessions/{demo}/insights").json()
    assert response["claims"] == [] and response["psychology"] is None


def test_completed_stream_is_saved_when_question_style_budget_is_exceeded(client, app, monkeypatch):
    async def stream(task, data, usage):
        usage.append({'task': task, 'http_requests': 1})
        yield '晚上好。今天过得怎么样？现在想聊聊吗？'

    monkeypatch.setattr(app.state.service.gateway, 'stream', stream)
    sid = session(client)
    response = client.post(f'/v1/sessions/{sid}/messages/stream', json={
        'content': '晚上好', 'request_id': 'completed-style-warning', 'interaction_mode': 'online',
    })
    assert response.status_code == 200
    assert 'event: done' in response.text and 'event: error' not in response.text
    trace = json.loads(app.state.repo.rows('SELECT trace FROM turns')[0]['trace'])
    assert trace['style_warnings'] == ['question_budget_exceeded']
    history = client.get(f'/v1/sessions/{sid}/messages').json()['items']
    assert history[-1]['content'].endswith('现在想聊聊吗？')


def test_book_delivery_events_and_action_context_are_supported(client):
    sid = session(client)
    response = client.post(f'/v1/sessions/{sid}/scene-events', json={'events': [{
        'id': 'delivered-book-event', 'action': 'deliver_book', 'actor': 'boss',
        'description': '林予把书递给朋友',
    }]})
    assert response.status_code == 200
