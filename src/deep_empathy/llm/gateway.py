import asyncio
import json
import time
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from deep_empathy.domain.errors import AppError
from deep_empathy.orchestration.capabilities import CapabilityStream
from deep_empathy.prompts.templates import BASE, COMMON, PROMPTS


class CloudLLM:
    """OpenAI-compatible chat-completions transport; no vendor SDK or local model."""

    def __init__(self, settings, client=None, background=False):
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.llm_timeout, connect=10),
            limits=httpx.Limits(max_connections=settings.max_llm_concurrency),
            follow_redirects=False,
        )
        self.semaphore = asyncio.Semaphore(1 if background else settings.max_llm_concurrency)

    async def close(self):
        await self.client.aclose()

    def validate_config(self):
        s = self.settings
        if not s.configured:
            raise AppError(
                "LLM_NOT_CONFIGURED", "尚未配置云端模型，请在 .env 填写 API 地址、密钥和模型名。", 503
            )
        parsed = urlparse(s.llm_base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.query or parsed.fragment:
            raise AppError("LLM_CONFIG_INVALID", "云端 API 地址格式无效。", 503)
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise AppError("LLM_CONFIG_INVALID", "远程云端 API 请使用 HTTPS。", 503)

    async def generate(self, task, data, schema, usage, repair=True):
        self.validate_config()
        s = self.settings
        model = s.task_models.get(task) or s.llm_model
        system = (
            BASE
            + PROMPTS[task]
            + "\nJSON schema:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ]
        # One bounded schema repair. Invalid responses never enter persistent user memory.
        for repair_index in range(2 if repair else 1):
            payload = {
                "temperature": 0.4,
                **s.llm_extra_body,
                "model": model,
                "messages": messages,
                "max_tokens": 1400 if task == "prepare" else 2200,
            }
            if task == "analysis" and (urlparse(s.llm_base_url).hostname or "").endswith("aliyuncs.com") and model.startswith("qwen3.7-"):
                payload.setdefault("enable_thinking", False)
            if s.json_mode:
                payload["response_format"] = {"type": "json_object"}
            started = time.monotonic()
            async with self.semaphore:
                response = await self._request(payload)
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                tokens = body.get("usage") or {}
                usage.append(
                    {
                        "task": task,
                        "model": model,
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                        "prompt_tokens": tokens.get("prompt_tokens", 0),
                        "completion_tokens": tokens.get("completion_tokens", 0),
                        "http_requests": response.extensions.get("deep_empathy_attempts", 1),
                    }
                )
                if not isinstance(content, str):
                    raise TypeError("missing text")
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0]
                return schema.model_validate_json(content)
            except (ValueError, KeyError, IndexError, TypeError, AttributeError, ValidationError):
                if repair and repair_index == 0:
                    messages.append(
                        {"role": "user", "content": "上次输出不符合 JSON schema，请重新输出有效对象。"}
                    )
        raise AppError("LLM_INVALID_OUTPUT", "云端模型返回格式异常，请稍后重试。", 502)

    async def stream(self, task, data, usage):
        """Forward real content deltas. Never retry after exposing any text."""
        self.validate_config()
        s = self.settings
        model = s.task_models.get(task) or s.task_models.get("generation") or s.llm_model
        payload = {
            "temperature": 0.4,
            **s.llm_extra_body,
            "model": model,
            "stream": True,
            "max_tokens": s.reply_max_tokens,
            "messages": [
                {"role": "system", "content": COMMON + PROMPTS[task]},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
            ],
        }
        if task == "respond":
            # Qwen hybrid reasoning delays visible content. Only tune this known provider/model.
            host = urlparse(s.llm_base_url).hostname or ""
            if host.endswith("aliyuncs.com") and model.startswith("qwen3.7-"):
                payload.setdefault("enable_thinking", False)
            payload.update(s.respond_extra_body)
        if s.stream_usage:
            payload["stream_options"] = {"include_usage": True}
        started, exposed, length = time.monotonic(), False, 0
        upstream_ttft_ms = None
        for attempt in range(3):
            tokens, finish = {}, None
            capability_stream = CapabilityStream()
            try:
                async with self.semaphore:
                    request_started = time.monotonic()
                    async with self.client.stream(
                        "POST",
                        s.llm_base_url + "/chat/completions",
                        headers={"Authorization": f"Bearer {s.llm_api_key}"},
                        json=payload,
                    ) as response:
                        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                            await asyncio.sleep(0.25 * 2**attempt)
                            continue
                        self._check_status(response)
                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if raw == "[DONE]":
                                break
                            if not raw:
                                continue
                            try:
                                chunk = json.loads(raw)
                                if chunk.get("error"):
                                    raise AppError("LLM_STREAM_ERROR", "回复生成中断，可以重试。", 502)
                                tokens = chunk.get("usage") or tokens
                                choices = chunk.get("choices") or []
                                if not choices:
                                    continue
                                choice = choices[0]
                                finish = choice.get("finish_reason") or finish
                                text = (choice.get("delta") or {}).get("content")
                                # reasoning_content is intentionally never forwarded or saved.
                                if text:
                                    if not isinstance(text, str):
                                        raise ValueError("invalid delta")
                                    length += len(text)
                                    if length > 4000:
                                        raise AppError("LLM_OUTPUT_LIMIT", "回复超出长度限制，请重试。", 502)
                                    if upstream_ttft_ms is None:
                                        upstream_ttft_ms = round((time.monotonic() - request_started) * 1000)
                                    exposed = True
                                    visible = capability_stream.feed(text) if task == "respond" else text
                                    if visible:
                                        yield visible
                            except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                                raise AppError(
                                    "LLM_INVALID_STREAM", "云端流式格式异常，请重试。", 502
                                ) from None
                        if finish != "stop" or not exposed:
                            raise AppError("LLM_STREAM_INCOMPLETE", "回复未完整生成，请重试。", 502)
                        if task == "respond":
                            tail = capability_stream.finish()
                            if tail:
                                yield tail
                        usage.append(
                            {
                                "task": task,
                                "model": model,
                                "stream": True,
                                "capability_usage": capability_stream.records() if task == "respond" else [],
                                "latent_psychology": capability_stream.psychology(data.get("current", {}).get("content", "")) if task == "respond" else None,
                                "upstream_ttft_ms": upstream_ttft_ms,
                                "elapsed_ms": round((time.monotonic() - started) * 1000),
                                "prompt_tokens": tokens.get("prompt_tokens", 0),
                                "completion_tokens": tokens.get("completion_tokens", 0),
                                "usage_reported": bool(tokens),
                                "http_requests": attempt + 1,
                            }
                        )
                        return
            except httpx.RequestError:
                if exposed or attempt == 2:
                    raise AppError("LLM_UNAVAILABLE", "回复连接中断，请重试。", 503) from None
                await asyncio.sleep(0.25 * 2**attempt)

    @staticmethod
    def _check_status(response):
        if response.status_code in (401, 403):
            raise AppError("LLM_AUTH_ERROR", "云端模型鉴权失败，请检查服务端 API 配置。", 503)
        if response.status_code == 429:
            raise AppError("LLM_RATE_LIMIT", "云端模型暂时繁忙，请稍后重试。", 503)
        if response.status_code >= 300:
            raise AppError("LLM_UPSTREAM_ERROR", "云端模型请求失败，请检查接口兼容性。", 502)

    async def _request(self, payload):
        for attempt in range(3):
            try:
                response = await self.client.post(
                    self.settings.llm_base_url + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
                    json=payload,
                )
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                if response.status_code in (401, 403):
                    raise AppError("LLM_AUTH_ERROR", "云端模型鉴权失败，请检查服务端 API 配置。", 503)
                if response.status_code == 429:
                    raise AppError("LLM_RATE_LIMIT", "云端模型暂时繁忙，请稍后重试。", 503)
                if response.status_code >= 300:
                    raise AppError(
                        "LLM_UPSTREAM_ERROR", "云端模型请求失败，请检查地址、模型名及接口兼容性。", 502
                    )
                response.extensions["deep_empathy_attempts"] = attempt + 1
                return response
            except httpx.RequestError:
                if attempt == 2:
                    raise AppError(
                        "LLM_UNAVAILABLE", "云端模型连接超时或网络不可用，请稍后重试。", 503
                    ) from None
                await asyncio.sleep(0.5 * (2**attempt))
        raise AppError("LLM_UNAVAILABLE", "云端模型暂时不可用。", 503)
