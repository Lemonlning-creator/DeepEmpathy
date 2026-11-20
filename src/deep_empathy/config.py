"""Configuration is read on startup; secrets never reach the browser."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    database_path: str = "data/deep_empathy.db"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    demo_enabled: bool = False
    test_reset_on_reload: bool = False
    weather_enabled: bool = True
    weather_location: str = "广州"
    weather_latitude: float = 23.1291
    weather_longitude: float = 113.2644
    cookie_secure: bool = False
    llm_timeout: float = 45
    turn_timeout: float = 180
    max_llm_concurrency: int = 4
    max_context_chars: int = 18000
    json_mode: bool = True
    reply_max_tokens: int = 600
    background_enabled: bool = True
    background_interval: int = 4
    background_timeout: float = 120
    background_poll_seconds: float = 1
    stream_usage: bool = False
    llm_extra_body: dict = field(default_factory=dict)
    respond_extra_body: dict = field(default_factory=dict)
    task_models: dict = field(default_factory=dict)
    memory_provider: str = "disabled"
    memory_path: str = "data/mem0"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dims: int = 1024
    memory_search_timeout: float = 1.2
    memory_top_k: int = 8
    memory_context_chars: int = 2500
    initial_profile: dict = field(default_factory=dict)
    persona: dict = field(default_factory=dict)
    defe: dict = field(default_factory=dict)

    @property
    def configured(self):
        return bool(self.llm_base_url and self.llm_api_key and self.llm_model)

    @classmethod
    def from_env(cls, *, prefer_project_env=False):
        load_dotenv(ROOT / ".env", override=prefer_project_env)

        def read(name):
            path = ROOT / "configs" / name
            return yaml.safe_load(path.read_text()) if path.exists() else {}

        url = os.getenv("DATABASE_URL", "sqlite:///./data/deep_empathy.db")
        if not url.startswith("sqlite:///"):
            raise ValueError("This release supports sqlite:/// database URLs only")
        llm_url = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")
        dashscope = (urlparse(llm_url).hostname or "").endswith("aliyuncs.com")
        provider = os.getenv("MEMORY_PROVIDER", "mem0").strip()
        if provider not in ("mem0", "disabled"):
            raise ValueError("MEMORY_PROVIDER must be mem0 or disabled")
        return cls(
            memory_provider=provider,
            memory_path=os.getenv("MEMORY_PATH", str(ROOT / "data/mem0")),
            embedding_base_url=os.getenv("MEMORY_EMBEDDING_BASE_URL", llm_url).strip().rstrip("/"),
            embedding_api_key=os.getenv("MEMORY_EMBEDDING_API_KEY", os.getenv("LLM_API_KEY", "")).strip(),
            embedding_model=os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-v4" if dashscope else "").strip(),
            embedding_dims=int(os.getenv("MEMORY_EMBEDDING_DIMS", "1024")),
            memory_search_timeout=max(.05, float(os.getenv("MEMORY_SEARCH_TIMEOUT", "1.2"))),
            memory_top_k=max(1, min(20, int(os.getenv("MEMORY_TOP_K", "8")))),
            memory_context_chars=max(500, min(6000, int(os.getenv("MEMORY_CONTEXT_CHARS", "2500")))),
            weather_enabled=os.getenv("WEATHER_ENABLED", "true").lower() == "true",
            weather_location=os.getenv("WEATHER_LOCATION", "广州"),
            weather_latitude=float(os.getenv("WEATHER_LATITUDE", "23.1291")),
            weather_longitude=float(os.getenv("WEATHER_LONGITUDE", "113.2644")),
            database_path=url.removeprefix("sqlite:///"),
            llm_base_url=os.getenv("LLM_BASE_URL", "").strip().rstrip("/"),
            llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
            llm_model=os.getenv("LLM_MODEL", "").strip(),
            demo_enabled=os.getenv("DEMO_ENABLED", "false").lower() == "true",
            test_reset_on_reload=os.getenv("TEST_RESET_ON_RELOAD", "false").lower() == "true",
            cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
            llm_timeout=float(os.getenv("LLM_TIMEOUT", "45")),
            turn_timeout=float(os.getenv("TURN_TIMEOUT", "180")),
            json_mode=os.getenv("LLM_JSON_MODE", "true").lower() == "true",
            reply_max_tokens=int(os.getenv("REPLY_MAX_TOKENS", "600")),
            background_enabled=os.getenv("BACKGROUND_ENABLED", "true").lower() == "true",
            background_interval=max(1, int(os.getenv("BACKGROUND_INTERVAL", "4"))),
            background_timeout=float(os.getenv("BACKGROUND_TIMEOUT", "120")),
            stream_usage=os.getenv("LLM_STREAM_USAGE", "false").lower() == "true",
            llm_extra_body=json.loads(os.getenv("LLM_EXTRA_BODY", "{}")),
            respond_extra_body=json.loads(os.getenv("LLM_RESPOND_EXTRA_BODY", "{}")),
            task_models={
                task: os.getenv(f"LLM_MODEL_{task.upper()}", "").strip()
                for task in (
                    "respond",
                    "prepare",
                    "analysis",
                    "planning",
                    "generation",
                    "review",
                    "summarization",
                    "evaluation",
                )
            },
            initial_profile=read("initial_profile.yaml"),
            persona=read("persona.yaml"),
            defe=read("defe.yaml"),
        )
