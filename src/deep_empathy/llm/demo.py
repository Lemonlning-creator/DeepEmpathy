"""Explicit scripted UI walkthrough. No inference and no network calls."""

import asyncio

from deep_empathy.domain.models import Analysis, Preparation, Psychology, Reply, Review, Summary, SupportPlan

DEMO_INPUTS = [
    "最近总忍不住和别人比较，觉得自己做得还不够好。",
    "我只是想说说，暂时不需要建议。",
    "其实我在意的不是超过别人，而是能按自己的节奏进步。",
]


class DemoLLM:
    async def generate(self, task, data, schema, usage, repair=True):
        if task == "prepare":
            return Preparation(
                analysis=await DemoLLM.generate(self, "analysis", data, Analysis, []),
                plan=await DemoLLM.generate(self, "planning", data, SupportPlan, []),
            )
        usage.append(
            {
                "task": task,
                "model": "scripted-demo",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "elapsed_ms": 0,
            }
        )
        text = data.get("current", {}).get("content", "")
        index = DEMO_INPUTS.index(text) if text in DEMO_INPUTS else -1
        if task == "analysis":
            return Analysis(
                emotion="示例：比较带来的压力" if index == 0 else "演示脚本，不分析自由输入",
                event="固定示例",
                support_preference="listen" if index == 1 else "unknown",
                psychology=Psychology(),
            )
        if task == "planning":
            return SupportPlan(
                goal="演示先倾听再确认的交互",
                validation="承接表达",
                user_perspective="不做心理推断",
                agent_constraints=["明确演示性质"],
                style="温和简洁",
                ask_clarification=False,
                offer_advice=False,
                avoid_assertions=[],
            )
        if task == "generation":
            replies = [
                "看到别人往前走时，自己的努力好像一下就变得不够了。反复比较，确实会让人很累。我们可以先不急着评判自己，把这份‘还不够好’慢慢说出来。",
                "好，先不找方法，也不用急着调整自己。你可以照自己的节奏说，我会把注意力放在听你讲这件事上。",
                "谢谢你把这点说清楚。你更在意的是自己的成长节奏，而不是赢过谁。刚才的理解需要往这里调整，也不用把别人的进度变成你的标准。",
            ]
            return Reply(
                text=replies[index]
                if index >= 0
                else "这是一段界面演示，当前没有调用大模型，也不会分析你的输入。你可以点击下方的示例话题体验交互；配置云端 API 后，再开启真实对话。"
            )
        if task == "review":
            return Review(passed=True)
        if task == "summarization":
            return Summary(text="固定脚本演示", source_message_ids=[])
        raise ValueError(task)

    async def stream(self, task, data, usage):
        reply = await DemoLLM.generate(self, "generation", data, Reply, usage)
        usage[-1]["task"] = task
        for offset in range(0, len(reply.text), 12):
            yield reply.text[offset : offset + 12]
            await asyncio.sleep(0)
