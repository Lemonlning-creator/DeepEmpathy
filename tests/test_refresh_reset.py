from pathlib import Path

import yaml
from conftest import send, session
from test_mem0_memory import manager

from deep_empathy.api.app import COOKIE


def test_test_reload_erases_old_data_restores_seed_and_purges_mem0(client, app):
    app.state.settings.test_reset_on_reload = True
    app.state.settings.initial_profile = yaml.safe_load(Path('configs/initial_profile.yaml').read_text())
    client.post('/v1/bootstrap')
    repo, service = app.state.repo, app.state.service
    old = repo.authenticate(client.cookies.get(COOKIE))['id']
    baseline = {x['statement'] for x in repo.profile(old)}
    assert len(baseline) == 11
    sid = session(client)
    send(client, sid, '我希望你先听我说。', 'before-test-refresh')
    assert len(repo.profile(old)) > len(baseline)
    # Exercise a populated Mem0 projection, not just an empty SQLite history.
    service.memory = manager(app)
    memory = service.memory
    memory.enqueue(old)
    client.portal.call(memory.step)
    assert any(x['owner'] == old for x in memory.store.items.values())
    other, _ = repo.create_user()
    job = repo.rows('SELECT * FROM model_jobs WHERE user_id=? LIMIT 1', (old,))[0]
    with repo.connect() as db:
        db.execute("UPDATE model_jobs SET status='running' WHERE id=?", (job['id'],))
    assert service.jobs.valid(job)
    result = client.post('/v1/bootstrap?reset_for_test=1')
    assert result.status_code == 200 and result.json()['test_reset_on_reload'] is True
    new = repo.authenticate(client.cookies.get(COOKIE))['id']
    assert new != old
    for table in ('users', 'sessions', 'messages', 'claims', 'evidence', 'turns', 'summaries', 'model_jobs', 'profile_initializations'):
        key = 'id' if table == 'users' else 'user_id'
        assert repo.rows(f'SELECT * FROM {table} WHERE {key}=?', (old,)) == []
    assert not service.jobs.valid(job)  # An already running analysis cannot commit stale results.
    assert {x['statement'] for x in repo.profile(new)} == baseline
    assert client.get('/v1/sessions').json()  # Only the synthetic seed session remains.
    assert client.get(f'/v1/sessions/{sid}/messages').status_code == 404
    assert repo.user(other)['id'] == other
    client.portal.call(memory.step)
    assert not any(x['owner'] == old for x in memory.store.items.values())
    assert memory.documents(new) and all(x['kind'] == 'semantic' for x in memory.documents(new).values())


def test_normal_bootstrap_and_disabled_test_mode_preserve_data(client, app):
    sid = session(client)
    send(client, sid, '你好', 'preserved-round')
    old_cookie = client.cookies.get(COOKIE)
    client.post('/v1/bootstrap?reset_for_test=1')
    assert client.cookies.get(COOKIE) == old_cookie
    assert client.get(f'/v1/sessions/{sid}/messages').json()['items']
    app.state.settings.test_reset_on_reload = True
    client.post('/v1/bootstrap')  # API clients are not page refreshes.
    assert client.cookies.get(COOKIE) == old_cookie
