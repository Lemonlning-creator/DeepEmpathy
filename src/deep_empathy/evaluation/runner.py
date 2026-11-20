"""Explicit opt-in cloud evaluation of JSONL cases. No access to live user records."""

import argparse
import asyncio
import json
from pathlib import Path

from deep_empathy.config import Settings
from deep_empathy.domain.models import Evaluation
from deep_empathy.llm.gateway import CloudLLM
from deep_empathy.prompts.templates import VERSION


async def evaluate(source, destination):
    settings = Settings.from_env()
    gateway = CloudLLM(settings)
    results = []
    try:
        for line in Path(source).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            if not all(key in case for key in ("id", "current", "reply")):
                raise ValueError("Each case requires id, current and reply")
            usage = []
            score = await gateway.generate("evaluation", case, Evaluation, usage)
            item = {"id": case["id"], **score.model_dump(), "prompt_version": VERSION, "usage": usage}
            item["average"] = (score.resonation + score.expression + score.reception) / 3
            results.append(item)
    finally:
        await gateway.close()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in results) + "\n", encoding="utf-8")
    print(f"Evaluated {len(results)} cases; written to {target}")


def main():
    parser = argparse.ArgumentParser(description="Opt-in cloud empathy evaluation")
    parser.add_argument("source", help="JSONL containing id, current, reply and optional evidence/history")
    parser.add_argument("destination")
    args = parser.parse_args()
    asyncio.run(evaluate(args.source, args.destination))


if __name__ == "__main__":
    main()
