import pytest
from fastapi.testclient import TestClient

from deep_empathy.api.app import create_app
from deep_empathy.config import Settings
from deep_empathy.domain.models import Analysis, Citation, ClaimProposal, Psychology
from deep_empathy.llm.demo import DemoLLM

HEADERS = {"X-Deep-Empathy": "1"}


class FakeCloud(DemoLLM):
    """Deterministic contract fixture, never used as a production fallback."""

    def __init__(self):
        self.calls = []
        self.fail_task = None

    async def generate(self, task, data, schema, usage, repair=True):
        from deep_empathy.domain.errors import AppError

        self.calls.append((task, data))
        if task == self.fail_task:
            raise AppError("LLM_UNAVAILABLE", "fixture failure", 503)
        if task == "analysis":
            message = data["current"]
            citation = Citation(message_id=message["id"], quote=message["content"])
            return Analysis(
                emotion="难过",
                event="用户表达",
                support_preference="listen",
                claims=[
                    ClaimProposal(
                        layer="behavior", statement="倾诉时希望先被倾听", citations=[citation], explicit=True
                    )
                ],
                psychology=Psychology(
                    needs=["relatedness"], interpretation="可能希望被倾听", citations=[citation]
                ),
            )
        return await super().generate(task, data, schema, usage)

    async def stream(self, task, data, usage):
        from deep_empathy.domain.errors import AppError

        self.calls.append((task, data))
        if self.fail_task in ("respond", "generation"):
            raise AppError("LLM_UNAVAILABLE", "fixture failure", 503)
        usage.append({"task": task, "model": "fixture", "http_requests": 1})
        for text in ["听起来这件事让你有些累，", "我们可以先慢慢说。"]:
            yield text

    async def close(self):
        pass


@pytest.fixture
def app(tmp_path):
    settings = Settings(
        database_path=str(tmp_path / "test.db"),
        demo_enabled=True,
        llm_base_url="https://example.test/v1",
        llm_api_key="test",
        llm_model="test",
    )
    return create_app(settings, gateway=FakeCloud())


@pytest.fixture
def client(app):
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/v1/bootstrap").status_code == 200
        yield client


def session(client, mode="cloud"):
    return client.post("/v1/sessions", json={"mode": mode}).json()["id"]


def send(client, sid, text="我希望你先听我说说", key="request-0001"):
    response = client.post(f"/v1/sessions/{sid}/messages", json={"content": text, "request_id": key})
    if response.status_code == 200:
        client.portal.call(client.app.state.service.jobs.drain)
    return response
