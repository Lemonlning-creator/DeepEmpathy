import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from deep_empathy.config import Settings
from deep_empathy.weather import ShopWeather, describe


def payload(code=63):
    return {'current': {'weather_code': code, 'temperature_2m': 7.5, 'time': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                        'is_day': 1, 'rain': 2.3, 'snowfall': 0, 'wind_speed_10m': 4}}


@pytest.mark.asyncio
async def test_weather_is_cached_singleflight_and_does_not_call_a_model():
    calls = []

    async def handle(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    service = ShopWeather(Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    values = await asyncio.gather(*[service.current() for _ in range(5)])
    assert len(calls) == 1
    assert all(v['kind'] == 'rain' and v['status'] == 'live' for v in values)
    assert calls[0].url.params['latitude'] == '23.1291'
    await service.close()


@pytest.mark.asyncio
async def test_network_failure_uses_labeled_cache_then_expires_without_fake_sun():
    tick, calls = [0], []

    def handle(request):
        calls.append(1)
        return httpx.Response(200, json=payload()) if len(calls) == 1 else httpx.Response(503)

    service = ShopWeather(Settings(), httpx.AsyncClient(transport=httpx.MockTransport(handle)), clock=lambda: tick[0])
    await service.current()
    tick[0] = 601
    result = await service.current()
    assert result['status'] == 'stale' and result['kind'] == 'rain'
    await service.current()
    assert len(calls) == 2  # Backoff prevents repeated requests during an outage.
    tick[0] = 7201
    result = await service.current()
    assert result['status'] == 'unavailable' and result['kind'] == 'unknown'
    await service.close()


@pytest.mark.asyncio
async def test_invalid_weather_and_disabled_mode_fail_closed():
    async def handle(request):
        bad = payload()
        bad['current']['temperature_2m'] = 'NaN'
        return httpx.Response(200, json=bad)

    settings = Settings()
    service = ShopWeather(settings, httpx.AsyncClient(transport=httpx.MockTransport(handle)))
    assert (await service.current())['kind'] == 'unknown'
    settings.weather_enabled = False
    assert (await service.current())['status'] == 'disabled'
    await service.close()


def test_precipitation_types_are_not_confused():
    assert describe(95)[0] == 'storm'
    assert describe(73)[0] == 'snow'
    assert describe(45)[0] == 'fog'
    assert describe(0)[0] == 'clear'
    assert describe(999)[0] == 'unknown'


def test_displayed_snapshot_is_pinned_into_generation_and_stream_meta(client, app):
    import json

    from conftest import session

    weather = app.state.weather
    displayed = weather.remember({'status': 'live', 'kind': 'rain', 'label': '雨', 'location': '广州',
                                  'temperature_c': 21, 'observed_at': '2026-11-19T18:00', 'source': 'Open-Meteo'})
    # A background refresh changes the current cache, but this user's scene is still the older snapshot.
    weather.cached = {'status': 'live', 'kind': 'clear', 'location': '广州', 'label': '晴'}
    weather.fetched = weather.clock()
    sid = session(client)
    response = client.post(f'/v1/sessions/{sid}/messages/stream', json={
        'content': '书屋外面是什么天气？', 'request_id': 'weather-shared-snapshot',
        'weather_snapshot_id': displayed['snapshot_id'],
    })
    assert response.status_code == 200
    meta = next(json.loads(block.split('data: ', 1)[1]) for block in response.text.split('\n\n') if block.startswith('event: meta'))
    data = next(data for task, data in app.state.service.gateway.calls if task == 'respond')
    assert data['interaction']['weather'] == displayed == meta['weather']
    assert data['interaction']['mode'] == 'online'
    trace = json.loads(app.state.repo.rows('SELECT trace FROM turns WHERE session_id=?', (sid,))[0]['trace'])
    assert trace['interaction']['weather'] == displayed
    assert len([task for task, _ in app.state.service.gateway.calls if task == 'respond']) == 1


def test_weather_preview_requires_test_mode_and_is_not_reported_as_real(client, app):
    from conftest import session

    weather = app.state.weather
    weather.cached = {'status': 'live', 'kind': 'clear', 'location': '广州', 'label': '晴'}
    weather.fetched = weather.clock()
    sid = session(client)
    for allowed in (False, True):
        app.state.settings.test_reset_on_reload = allowed
        result = client.post(f'/v1/sessions/{sid}/messages', json={
            'content': '窗外怎么样？', 'request_id': f'weather-preview-{allowed}', 'weather_preview': 'rain',
        })
        assert result.status_code == 200
        data = [data for task, data in app.state.service.gateway.calls if task == 'respond'][-1]
        state = data['interaction']['weather']
        assert state['is_preview'] == allowed
        assert state['kind'] == ('rain' if allowed else 'clear')
        assert state['location'] == '广州'


def test_snapshot_expiry_and_missing_data_do_not_block_chat_or_invent_weather():
    tick = [0]
    service = ShopWeather(Settings(), clock=lambda: tick[0])
    snap = service.remember({'status': 'live', 'kind': 'rain', 'label': '雨'})
    tick[0] = 7201
    assert service.context(snap['snapshot_id'])['kind'] == 'unknown'
    for i in range(100):
        service.remember({'kind': 'clear', 'sequence': i})
    assert len(service.snapshots) == 64
