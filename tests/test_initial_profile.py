from pathlib import Path

import yaml
from conftest import session

from deep_empathy.domain.models import ClaimProposal
from deep_empathy.user_model.profile import prepare_claims


def test_initial_profile_imports_once_with_real_source_and_reaches_cloud(client, app):
    seed = yaml.safe_load((Path(__file__).resolve().parents[1]/'configs/initial_profile.yaml').read_text())
    app.state.settings.initial_profile = seed
    assert client.post('/v1/bootstrap').status_code == 200
    claims = app.state.repo.rows('SELECT * FROM claims')
    assert len(claims) == 11
    assert {c['layer'] for c in claims} == {'core','regulation','cognition','identity','behavior'}
    evidence = app.state.repo.rows('SELECT * FROM evidence')
    assert all(e['message_id'] is None and e['source_type'] == 'initial_profile' for e in evidence)
    assert not app.state.repo.rows('SELECT * FROM messages')
    cid = claims[-1]['id']
    assert client.patch(f'/v1/me/profile/claims/{cid}',json={'action':'retract'}).status_code == 200
    client.post('/v1/bootstrap')
    assert len(app.state.repo.rows('SELECT * FROM claims')) == 11
    assert app.state.repo.rows('SELECT status FROM claims WHERE id=?',(cid,))[0]['status']=='retracted'
    sid=session(client)
    response=client.post(f'/v1/sessions/{sid}/messages',json={'content':'中午好','request_id':'seed-context-test'})
    assert response.status_code == 200
    data=app.state.service.gateway.calls[0][1]
    assert any('周禾' in c['statement'] for c in data['profile'])


def test_explicit_seed_correction_does_not_require_two_synthetic_sessions():
    old={'id':'seed-core','status':'supported','layer':'core','statement':'害怕失败',
         'evidence':[{'source_type':'initial_profile'}]}
    messages=[{'id':'real-user','role':'user','session_id':'one','content':'纠正一下，我并不害怕失败，我接受失败。'}]
    proposal=ClaimProposal(layer='core',statement='接受失败',explicit=True,replaces_id='seed-core',
                          citations=[{'message_id':'real-user','quote':'我接受失败'}])
    prepared,discarded=prepare_claims([proposal],messages,[old])
    assert not discarded and prepared[0]['supersedes_id']=='seed-core'
    proposal.explicit=False
    assert prepare_claims([proposal],messages,[old])[1]==1


def test_agent_baseline_replaces_setting_without_exposing_unknown_secrets(client, app):
    from deep_empathy.memory.context import build_context
    from deep_empathy.user_model.initial import initialize_profile

    root=Path(__file__).resolve().parents[1]
    owner=app.state.repo.rows('SELECT id FROM users')[0]['id']
    old=yaml.safe_load((root/'configs/user_setting.yaml').read_text())
    new=yaml.safe_load((root/'configs/initial_profile.yaml').read_text())
    initialize_profile(app.state.repo,owner,old)
    app.state.settings.initial_profile=new
    client.post('/v1/bootstrap')
    claims=app.state.repo.profile(owner)
    assert len(claims)==11
    assert len([c for c in claims if c['status']=='tentative'])==5
    assert all(c['confidence']==.35 for c in claims if c['status']=='tentative')
    assert app.state.repo.rows("SELECT COUNT(*) AS n FROM claims WHERE status='superseded'")[0]['n']==18
    client.post('/v1/bootstrap')
    assert len(app.state.repo.profile(owner))==11
    sid=session(client)
    context=build_context(app.state.repo,owner,sid,'今天你好',True,10000,'cloud')
    import json
    visible=json.dumps(context,ensure_ascii=False)
    assert '辜负他人的期待' not in visible
    assert '25岁' not in visible
    assert '核心需求尚不明确' not in [c['statement'] for c in claims]
    assert '初步推测' in visible and '已观察' in visible
