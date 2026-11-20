from conftest import send, session

from deep_empathy.orchestration.capabilities import MARKER, CapabilityStream


def test_structured_capabilities_are_separated_at_every_chunk_boundary():
    import json
    body = '听起来挺不容易的。愿意的话，接着聊聊。'
    metadata = json.dumps({'capabilities': [{'id': 'empathetic_response', 'evidence': '接住感受并留出表达空间'}]}, ensure_ascii=False)
    raw = body + MARKER + metadata
    for width in range(1, len(raw) + 1):
        stream = CapabilityStream()
        visible = ''.join(stream.feed(raw[i:i+width]) for i in range(0, len(raw), width)) + stream.finish()
        assert visible == body
        assert stream.records()[0]['id'] == 'empathetic_response'
        assert stream.records()[0]['basis'] == 'model_self_report'


def test_missing_invalid_or_unknown_metadata_never_guesses_by_keywords():
    for trailer in ['', MARKER+'broken', MARKER+'{"capabilities":[{"id":"invented","evidence":"x"}]}']:
        stream = CapabilityStream()
        assert stream.feed('推荐《叫魂》。我在听。'+trailer)+stream.finish() == '推荐《叫魂》。我在听。'
        assert stream.records() == []


def test_latest_turn_metadata_does_not_reuse_older_psychology(client, app):
    sid = session(client)
    first = send(client, sid, '我希望你先听我说。', 'insight-grounded-round').json()
    current = client.get(f'/v1/sessions/{sid}/insights').json()['current_turn']
    assert current['id'] == first['turn_id']
    assert current['psychology']['citations']
    assert current['profile_updates'][0]['statement'] == '倾诉时希望先被倾听'
    assert current['profile_updates'][0]['change'] == '新增'
    # A subsequent ordinary turn has no background analysis yet; it must stay inactive.
    second = client.post(f'/v1/sessions/{sid}/messages', json={
        'content': '今天很好', 'request_id': 'insight-next-round',
    }).json()
    current = client.get(f'/v1/sessions/{sid}/insights').json()['current_turn']
    assert current['id'] == second['turn_id']
    assert current['psychology'] is None and current['profile_updates'] == []


def test_foreground_latent_requires_exact_current_user_evidence():
    import json
    stream = CapabilityStream()
    stream.feed('先歇一会儿。'+MARKER+json.dumps({'capabilities': [], 'latent_psychology': {
        'part': 'needs', 'state': '希望休息（暂时推测）', 'quote': '今天太累了'}}, ensure_ascii=False))
    assert stream.psychology('今天太累了，想休息。')['part'] == 'needs'
    assert stream.psychology('你好') is None
    stream.metadata = json.dumps({'capabilities': [], 'latent_psychology': None})
    assert stream.psychology('今天太累了') is None


def test_marker_does_not_require_a_preceding_line_break():
    stream = CapabilityStream()
    visible = stream.feed('你好。[CAPABILITIES]\n{"capabilities":[{"id":"relationship_care","evidence":"关心后续"}],"latent_psychology":null}')
    assert visible == '你好。'
    assert stream.records()[0]['id'] == 'relationship_care'
