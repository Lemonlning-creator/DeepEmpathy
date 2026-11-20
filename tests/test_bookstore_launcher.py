import importlib.util
from pathlib import Path

from deep_empathy.config import Settings


def launcher():
    path = Path(__file__).resolve().parents[1] / 'scripts/preview_bookstore.py'
    spec = importlib.util.spec_from_file_location('bookstore_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bookstore_defaults_to_configured_backend(monkeypatch):
    configured = Settings(llm_base_url='https://example.test/v1', llm_api_key='test', llm_model='test')
    monkeypatch.setattr(Settings, 'from_env', lambda **kwargs: configured)
    assert launcher().bookstore_settings() is configured


def test_offline_qa_is_explicit_and_does_not_load_env(monkeypatch):
    def forbidden():
        raise AssertionError('Offline QA must not read credentials')

    monkeypatch.setattr(Settings, 'from_env', forbidden)
    settings = launcher().bookstore_settings(offline=True)
    assert settings.demo_enabled and not settings.configured
    assert settings.database_path.endswith('bookstore-preview.db')


def test_local_launcher_prefers_project_key_over_stale_shell(monkeypatch, tmp_path):
    import deep_empathy.config as config

    (tmp_path/'.env').write_text('LLM_API_KEY=project-test-key\nLLM_BASE_URL=https://example.test/v1\nLLM_MODEL=test-model\n')
    monkeypatch.setattr(config,'ROOT',tmp_path)
    monkeypatch.setenv('LLM_API_KEY','stale-shell-test-key')
    # Keep dotenv's environment mutation inside this test's monkeypatch lifetime.
    for name in ('LLM_BASE_URL','LLM_MODEL'):
        monkeypatch.setenv(name,'previous-test-value')
    settings=launcher().bookstore_settings()
    assert settings.llm_api_key=='project-test-key'
    assert settings.llm_base_url=='https://example.test/v1'
    assert settings.llm_model=='test-model'
