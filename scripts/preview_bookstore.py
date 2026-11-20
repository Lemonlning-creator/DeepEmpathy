"""Run the bookstore against the configured backend; --offline enables scripted QA."""

import argparse
from pathlib import Path

import uvicorn
import yaml

from deep_empathy.api.app import create_app
from deep_empathy.config import Settings


def bookstore_settings(*, offline=False):
    if not offline:
        # Local launcher: the project file is authoritative over stale shell exports.
        return Settings.from_env(prefer_project_env=True)
    # Explicit offline QA never reads .env and keeps its own disposable database.
    root = Path(__file__).resolve().parents[1]
    persona = yaml.safe_load((root / "configs/persona.yaml").read_text())
    return Settings(
        database_path=str(root / "data/bookstore-preview.db"), demo_enabled=True, persona=persona
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--offline", action="store_true", help="Use scripted demo without loading .env")
    args = parser.parse_args()
    uvicorn.run(create_app(bookstore_settings(offline=args.offline)), host="127.0.0.1", port=args.port)
