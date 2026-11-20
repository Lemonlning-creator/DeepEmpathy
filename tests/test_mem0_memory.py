import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from conftest import send, session

from deep_empathy.config import Settings
from deep_empathy.memory.long_term import LongTermMemory
from deep_empathy.memory.mem0_store import Mem0Store
from deep_empathy.storage.repository import invalidate_memory


class FakeStore:
    def __init__(self):
        self.items = {}
        self.search_override = None
        self.block = None
        self.started = asyncio.Event()
        self.search_calls = 0

    async def upsert(self, owner, doc, revision):
        self.started.set()
        if self.block:
            await self.block.wait()
        rid = uuid4().hex
        self.items[rid] = {'owner': owner, 'metadata': {
            **doc['metadata'], 'document_id': doc['id'], 'source_hash': doc['hash'], 'revision': revision,
        }}
        return rid

    async def search(self, owner, query, revision, limit):
        self.search_calls += 1
        return self.search_override if self.search_override is not None else [
            {'id': rid, **v} for rid, v in self.items.items() if v['owner'] == owner
        ][:limit]

    async def delete(self, rid):
        self.items.pop(rid, None)

    async def purge(self, owner):
        self.items = {k: v for k, v in self.items.items() if v['owner'] != owner}

    async def close(self):
        pass


def manager(app):
    s = app.state.settings
    s.memory_provider = 'mem0'
    s.embedding_api_key = 'fixture'
    s.embedding_base_url = 'https://example.test/v1'
    s.embedding_model = 'fixture-embedding'
    return LongTermMemory(app.state.repo, s, FakeStore())


def owner(app):
    return app.state.repo.rows('SELECT id FROM users')[0]['id']


def test_semantic_and_episodic_projection_are_incremental_and_retrievable(client, app):
    sid = session(client)
    send(client, sid, '我希望你先听我说，今天工作很累。', 'mem0-evidence-turn')
    m = manager(app)
    uid = owner(app)
    m.enqueue(uid)
    client.portal.call(m.step)
    docs = m.documents(uid)
    assert {d['kind'] for d in docs.values()} == {'semantic', 'episodic'}
    assert len(m.store.items) == len(docs)
    before = set(m.store.items)
    m.enqueue(uid)
    client.portal.call(m.step)
    assert set(m.store.items) == before
    recall = client.portal.call(m.recall, uid, '工作')
    assert recall['episodic'] and recall['semantic'] and recall['status'] == 'mem0'
    assert all('source_id' in item for item in recall['episodic'])


def test_retracted_and_deleted_sources_stop_retrieval_before_vector_cleanup(client, app):
    sid = session(client)
    send(client, sid, '我希望你先听我说，今天很累。', 'memory-delete-turn')
    m = manager(app)
    uid = owner(app)
    m.enqueue(uid)
    client.portal.call(m.step)
    claim = app.state.repo.profile(uid)[0]
    client.patch(f"/v1/me/profile/claims/{claim['id']}", json={'action': 'retract'})
    result = client.portal.call(m.recall, uid, '很累')
    assert not result['semantic'] and not result['episodic']  # old epoch rejected immediately
    m.enqueue(uid)
    client.portal.call(m.step)
    assert not client.portal.call(m.recall, uid, '很累')['semantic']
    client.delete(f'/v1/sessions/{sid}')
    result = client.portal.call(m.recall, uid, '很累')
    assert not result['episodic']
    m.enqueue(uid)
    client.portal.call(m.step)
    assert not m.store.items


def test_foreign_hits_and_tampered_metadata_never_enter_context(client, app):
    sid = session(client)
    send(client, sid, '我希望你听我说。', 'memory-isolation-turn')
    m = manager(app)
    uid = owner(app)
    m.enqueue(uid)
    client.portal.call(m.step)
    m.store.search_override = [{'metadata': {'document_id': 'semantic:foreign', 'revision': 0}},
                               {'metadata': {'document_id': next(iter(m.documents(uid))),
                                             'revision': 0, 'source_hash': 'tampered'}}]
    recall = client.portal.call(m.recall, uid, '记忆')
    assert not recall['semantic'] and not recall['episodic']


def test_memory_off_and_account_delete_physically_purge_vectors(client, app):
    sid = session(client)
    send(client, sid, '我希望你听我说。', 'memory-off-turn')
    m = manager(app)
    app.state.service.memory = m
    uid = owner(app)
    m.enqueue(uid)
    client.portal.call(m.step)
    assert m.store.items
    client.patch('/v1/me/memory-settings', json={'enabled': False})
    assert not client.portal.call(m.recall, uid, '任何事')['episodic']
    client.portal.call(m.step)
    assert not m.store.items
    client.patch('/v1/me/memory-settings', json={'enabled': True})
    client.portal.call(m.step)
    assert m.store.items
    client.delete('/v1/me/data')
    client.portal.call(m.step)
    assert not m.store.items
    assert client.post('/v1/me/memories/search', json={'query': '任何事'}).status_code == 401


def test_slow_memory_search_is_bounded_and_chat_still_uses_one_model_call(client, app):
    sid = session(client)
    m = manager(app)
    app.state.service.memory = m
    m.settings.memory_search_timeout = .02

    async def slow(*args):
        await asyncio.sleep(10)
    m.store.search = slow
    result = client.portal.call(m.recall, owner(app), 'test')
    assert result['status'] == 'unavailable'
    response = client.post(f'/v1/sessions/{sid}/messages', json={
        'content': '今天很好', 'request_id': 'slow-memory-foreground',
    })
    assert response.status_code == 200
    assert response.json()['processing']['foreground_calls'] == 1


def test_stale_background_write_is_unreadable_then_purged(client, app):
    sid = session(client)
    send(client, sid, '我希望你听我说。', 'memory-stale-turn')
    m = manager(app)
    uid = owner(app)

    async def race():
        m.store.block = asyncio.Event()
        m.enqueue(uid)
        task = asyncio.create_task(m.step())
        await m.store.started.wait()
        with m.repo.connect() as db:
            invalidate_memory(db, uid)
        m.store.block.set()
        await task
        result = await m.recall(uid, 'test')
        assert not result['semantic'] and not result['episodic']
        await m.step()
        revision = m.revision(uid)
        assert all(v['metadata']['revision'] == revision for v in m.store.items.values())
    client.portal.call(race)


@pytest.mark.asyncio
async def test_real_mem0_and_qdrant_roundtrip_without_llm_or_external_network(tmp_path, monkeypatch):
    # Actual Mem0 SDK and on-disk Qdrant. Only the remote embedding client is replaced.
    from deep_empathy.memory.long_term import document

    s = Settings(llm_base_url='https://example.test/v1', llm_api_key='fake', llm_model='fake',
                 memory_path=str(tmp_path/'mem0'), embedding_base_url='https://example.test/v1',
                 embedding_api_key='fake', embedding_model='fixture', embedding_dims=4)
    monkeypatch.setenv('MEM0_TELEMETRY', 'false')
    monkeypatch.setenv('MEM0_DIR', str(tmp_path/'runtime'))
    store = Mem0Store(s)
    calls = []

    class CloudFixture:
        def __init__(self):
            self.embeddings = self
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[1., 0., 0., 0.])])
        def close(self):
            pass

    try:
        def setup():
            m = store._memory()
            m.embedding_model.client.close()
            m.embedding_model.client = CloudFixture()
            def forbidden(*args, **kwargs):
                raise AssertionError('Mem0 must not run a second LLM extraction')
            m.llm.generate_response = forbidden
        await store._call(setup)
        doc = document('episodic', 'source', '昨天看过一本书', occurred_at='2026-11-17')
        rid = await store.upsert('alice', doc, 2)
        assert await store.upsert('alice', doc, 2) == rid
        assert len(calls) == 1
        results = await store.search('alice', '昨天读过什么', 2, 8)
        assert results[0]['metadata']['document_id'] == doc['id']
        assert not await store.search('bob', '昨天读过什么', 2, 8)
        assert all(c['model'] == 'fixture' and c['dimensions'] == 4 for c in calls)
        await store.purge('alice')
        assert not await store.search('alice', '书', 2, 8)
    finally:
        await store.close()


def test_sync_failure_is_durable_and_retry_recovers_without_duplicate_export(client, app):
    sid = session(client)
    send(client, sid, '我希望你听我说。', 'memory-retry-turn')
    m = manager(app)
    uid = owner(app)
    real = m.store.upsert

    async def broken(*args):
        raise RuntimeError('private provider error must not reach the user')
    m.store.upsert = broken
    m.enqueue(uid)
    client.portal.call(m.step)
    status = m.status(uid)
    assert status['index']['status'] == 'pending'
    assert status['index']['error_code'] == 'MEMORY_SYNC_FAILED'
    m.store.upsert = real
    with m.repo.connect() as db:
        db.execute("UPDATE memory_sync SET retry_after='' WHERE user_id=?", (uid,))
    client.portal.call(m.step)
    assert m.status(uid)['index']['status'] == 'completed'
    assert len(m.store.items) == len(m.documents(uid))


def test_memory_endpoints_are_authenticated_and_return_only_current_owner(client, app):
    sid = session(client)
    send(client, sid, '我希望你听我说。', 'memory-endpoint-turn')
    m = manager(app)
    app.state.service.memory = m
    uid = owner(app)
    m.enqueue(uid)
    client.portal.call(m.step)
    response = client.post('/v1/me/memories/search', json={'query': '说话'})
    assert response.status_code == 200 and response.json()['semantic']
    assert client.get('/v1/me/memory-status').json()['configured'] is True
    assert client.post('/v1/me/memories/search', json={'query': ''}).status_code == 422
    from fastapi.testclient import TestClient
    with TestClient(app, headers={'X-Deep-Empathy': '1'}) as stranger:
        assert stranger.post('/v1/me/memories/search', json={'query': '说话'}).status_code == 401
        stranger.post('/v1/bootstrap')
        result = stranger.post('/v1/me/memories/search', json={'query': '说话'}).json()
        assert not result['episodic'] and not result['semantic']
