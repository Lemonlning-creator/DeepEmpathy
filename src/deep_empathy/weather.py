"""Cached, non-LLM current weather. Location belongs to the shop, not the visitor."""
import asyncio
import hashlib
import json
import math
import time
from collections import OrderedDict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx


def describe(code):
    if code == 0:
        return 'clear', '晴'
    if code in (1, 2):
        return 'cloudy', '多云'
    if code == 3:
        return 'overcast', '阴'
    if code in (45, 48):
        return 'fog', '雾'
    if code in (71, 73, 75, 77, 85, 86):
        return 'snow', '雪'
    if code in (95, 96, 99):
        return 'storm', '雷雨'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return 'rain', '雨'
    return 'unknown', '天气未知'


class ShopWeather:
    def __init__(self, settings, client=None, clock=time.monotonic):
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=6)
        self.clock = clock
        self.lock = asyncio.Lock()
        self.cached = None
        self.fetched = None
        self.retry_at = 0
        self.snapshots = OrderedDict()

    async def close(self):
        await self.client.aclose()

    def fallback(self):
        if self.cached and self.clock() - self.fetched < 7200:
            return {**self.cached, 'status': 'stale', 'stale': True}
        return {'status': 'unavailable', 'stale': False, 'location': self.settings.weather_location,
                'kind': 'unknown', 'label': '天气暂不可用', 'source': 'Open-Meteo'}

    def remember(self, data):
        data = {**data, 'is_preview': False}
        key = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:24]
        data['snapshot_id'] = key
        if key not in self.snapshots:
            self.snapshots[key] = (self.clock(), data)
        self.snapshots.move_to_end(key)
        while len(self.snapshots) > 64:
            self.snapshots.popitem(last=False)
        return data

    def context(self, snapshot_id=None, preview=None):
        """Resolve the displayed snapshot without any network I/O on the reply path."""
        if preview:
            kind, label = {'clear': ('clear', '晴'), 'rain': ('rain', '雨'),
                           'snow': ('snow', '雪'), 'overcast': ('overcast', '阴')}[preview]
            return {'kind': kind, 'label': label, 'location': self.settings.weather_location,
                    'status': 'preview', 'is_preview': True, 'source': '测试场景预览', 'wind_ms': 3}
        if not self.settings.weather_enabled:
            return self.remember({'status': 'disabled', 'kind': 'unknown',
                                  'location': self.settings.weather_location, 'label': '天气未启用'})
        found = self.snapshots.get(snapshot_id)
        if found and self.clock() - found[0] < 7200:
            return found[1]
        if self.cached and self.clock() - self.fetched < 600:
            return self.remember(self.cached)
        return self.remember(self.fallback())

    async def current(self):
        if not self.settings.weather_enabled:
            return self.context()
        async with self.lock:
            tick = self.clock()
            if tick < self.retry_at:
                return self.remember(self.fallback())
            if self.cached and tick - self.fetched < 600:
                return self.remember(self.cached)
            try:
                response = await self.client.get('https://api.open-meteo.com/v1/forecast', params={
                    'latitude': self.settings.weather_latitude, 'longitude': self.settings.weather_longitude,
                    'current': 'temperature_2m,weather_code,is_day,precipitation,rain,snowfall,cloud_cover,wind_speed_10m',
                    'wind_speed_unit': 'ms', 'timezone': 'Asia/Shanghai',
                })
                response.raise_for_status()
                current = response.json()['current']
                code = int(current['weather_code'])
                temp = float(current['temperature_2m'])
                observed = datetime.fromisoformat(current['time'])
                # Reject malformed values rather than manufacture a sunny scene.
                if not math.isfinite(temp) or not -100 <= temp <= 70:
                    raise ValueError('invalid temperature')
                age = (datetime.now(timezone.utc) - observed.replace(tzinfo=observed.tzinfo or ZoneInfo('Asia/Shanghai')).astimezone(timezone.utc)).total_seconds()
                if age > 10800 or age < -3600:
                    raise ValueError('outdated current weather')
                kind, label = describe(code)
                self.cached = {'status': 'live', 'stale': False, 'location': self.settings.weather_location,
                               'kind': kind, 'label': label, 'code': code, 'temperature_c': temp,
                               'is_day': bool(current['is_day']), 'rain_mm': max(0, float(current.get('rain', 0))),
                               'snowfall_cm': max(0, float(current.get('snowfall', 0))),
                               'wind_ms': max(0, float(current.get('wind_speed_10m', 0))),
                               'observed_at': current['time'], 'fetched_at': datetime.now(timezone.utc).isoformat(),
                               'source': 'Open-Meteo', 'source_url': 'https://open-meteo.com/'}
                self.fetched = self.clock()
                self.retry_at = 0
                return self.remember(self.cached)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, OverflowError):
                self.retry_at = self.clock() + 60
                return self.remember(self.fallback())
