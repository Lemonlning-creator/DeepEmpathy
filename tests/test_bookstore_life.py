from datetime import datetime

import pytest

from deep_empathy.bookstore import ZONE, agenda


@pytest.mark.parametrize('clock,phase,opened', [
    ('08:59', 'closed', False), ('09:00', 'opening', True),
    ('09:30', 'shelves', True), ('11:00', 'reading', True),
    ('12:30', 'coffee', True), ('15:00', 'books', True),
    ('17:00', 'closing', True), ('18:00', 'closed', False),
    ('23:59', 'closed', False), ('00:00', 'closed', False),
])
def test_daily_boundaries(clock, phase, opened):
    state = agenda(datetime.fromisoformat(f'2026-11-12T{clock}').replace(tzinfo=ZONE))
    assert state['phase'] == phase
    assert state['open'] == state['lights_on'] == opened
    assert len(state['schedule']) == 6


def test_closed_shop_still_accepts_online_chat(client, monkeypatch):
    from conftest import session

    monkeypatch.setattr('deep_empathy.orchestration.service.agenda', lambda: {'open': False})
    sid = session(client)
    path = f'/v1/sessions/{sid}/messages'
    body = {'content': '今天过得不错', 'request_id': 'online-night', 'interaction_mode': 'online'}
    assert client.post(path, json=body).status_code == 200
    body.update(request_id='physical-night', interaction_mode='in_person')
    assert client.post(path, json=body).status_code == 409


def test_channel_and_real_agenda_reach_model(client, app):
    from conftest import session

    sid = session(client)
    response = client.post(f'/v1/sessions/{sid}/messages', json={
        'content': '今天过得不错', 'request_id': 'channel-context', 'interaction_mode': 'online',
    })
    assert response.status_code == 200
    data = app.state.service.gateway.calls[0][1]
    assert data['interaction']['mode'] == 'online'
    assert data['interaction']['store']['timezone'] == 'Asia/Shanghai'
    assert client.get('/v1/bookstore/agenda').status_code == 200


def test_daytime_in_person_is_forwarded_without_extra_call(client, app, monkeypatch):
    from conftest import session

    monkeypatch.setattr('deep_empathy.orchestration.service.agenda', lambda: {'open': True})
    sid = session(client)
    response = client.post(f'/v1/sessions/{sid}/messages', json={
        'content': '今天过得不错', 'request_id': 'physical-daytime', 'interaction_mode': 'in_person',
        'scene': {'user_present': True, 'boss_pose': 'standing', 'user_pose': 'standing',
                  'owner_activity': '整理书架', 'interruption': 'interacting'},
    })
    assert response.status_code == 200
    assert response.json()['processing']['foreground_calls'] == 1
    data = app.state.service.gateway.calls[0][1]
    assert data['interaction']['mode'] == 'in_person'
    assert data['bookstore_scene']['owner_activity'] == '整理书架'
