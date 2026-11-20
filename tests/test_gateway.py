import json

import httpx
import pytest

from deep_empathy.config import Settings
from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import Reply
from deep_empathy.llm.gateway import CloudLLM


def gateway(handler, **kwargs):
    settings = Settings(
        llm_base_url="https://api.example.test/v1", llm_api_key="secret", llm_model="cloud-test", **kwargs
    )
    return CloudLLM(settings, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.asyncio
async def test_cloud_schema_repair_and_task_model_route():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        content = '{"text":"收到"}' if len(calls) == 2 else '{"unexpected":true}'
        return httpx.Response(
            200, json={"choices": [{"message": {"content": content}}], "usage": {"prompt_tokens": 11}}
        )

    llm = gateway(handler, task_models={"generation": "another-cloud-model"})
    usage = []
    result = await llm.generate("generation", {"current": "你好"}, Reply, usage)
    assert result.text == "收到" and len(calls) == 2
    assert calls[0]["model"] == "another-cloud-model" and len(usage) == 2
    await llm.close()


@pytest.mark.asyncio
async def test_auth_failure_never_leaks_upstream_secret():
    llm = gateway(lambda request: httpx.Response(401, text="secret private upstream error"))
    with pytest.raises(AppError) as error:
        await llm.generate("generation", {}, Reply, [])
    assert error.value.code == "LLM_AUTH_ERROR" and "secret" not in error.value.message
    await llm.close()


@pytest.mark.asyncio
async def test_invalid_json_is_bounded():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    llm = gateway(handler)
    with pytest.raises(AppError) as error:
        await llm.generate("generation", {}, Reply, [])
    assert error.value.code == "LLM_INVALID_OUTPUT" and len(calls) == 2
    await llm.close()


@pytest.mark.asyncio
async def test_retry_transient_error():
    calls = []

    def handler(request):
        calls.append(1)
        return (
            httpx.Response(503)
            if len(calls) == 1
            else httpx.Response(200, json={"choices": [{"message": {"content": '{"text":"ok"}'}}]})
        )

    llm = gateway(handler)
    assert (await llm.generate("generation", {}, Reply, [])).text == "ok"
    assert len(calls) == 2
    await llm.close()


@pytest.mark.asyncio
async def test_qwen_foreground_disables_thinking_without_affecting_generic_providers():
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text='data: {"choices":[{"delta":{"content":"你好"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')

    llm = gateway(handler)
    llm.settings.llm_model = 'qwen3.7-plus'
    llm.settings.llm_base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    assert ''.join([v async for v in llm.stream('respond', {}, [])]) == '你好'
    assert bodies[-1]['enable_thinking'] is False
    llm.settings.respond_extra_body = {'enable_thinking': True}
    _ = [v async for v in llm.stream('respond', {}, [])]
    assert bodies[-1]['enable_thinking'] is True
    llm.settings.respond_extra_body = {}
    llm.settings.llm_base_url = 'https://example.test/v1'
    _ = [v async for v in llm.stream('respond', {}, [])]
    assert 'enable_thinking' not in bodies[-1]
    await llm.close()


@pytest.mark.asyncio
async def test_same_stream_returns_chat_and_model_capabilities_in_one_request():
    calls = []
    body = '这件事确实不容易。'
    raw = body + '\n[CAPABILITIES]' + json.dumps({'capabilities': [
        {'id': 'empathetic_response', 'evidence': '回应用户在事件中的感受'}], 'latent_psychology': {'part': 'self_view', 'state': '怀疑自己的能力（暂时推测）', 'quote': '觉得自己不行'}}, ensure_ascii=False)

    def handler(request):
        calls.append(json.loads(request.content))
        chunks = ['data: '+json.dumps({'choices': [{'delta': {'content': char}}]})+'\n\n' for char in raw]
        chunks.append('data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, text=''.join(chunks))

    llm = gateway(handler)
    usage = []
    assert ''.join([v async for v in llm.stream('respond', {'current': {'content': '我觉得自己不行。'}}, usage)]) == body
    assert len(calls) == 1
    assert usage[0]['capability_usage'][0]['id'] == 'empathetic_response'
    assert usage[0]['latent_psychology']['part'] == 'self_view'
    await llm.close()


@pytest.mark.asyncio
async def test_qwen_profile_analysis_disables_thinking_without_extra_requests():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"text":"ok"}'}}]})

    llm = gateway(handler)
    llm.settings.llm_model = 'qwen3.7-plus'
    llm.settings.llm_base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    await llm.generate('analysis', {}, Reply, [], repair=False)
    assert len(calls) == 1 and calls[0]['enable_thinking'] is False
    llm.settings.llm_extra_body = {'enable_thinking': True}
    await llm.generate('analysis', {}, Reply, [], repair=False)
    assert calls[-1]['enable_thinking'] is True
    await llm.close()
