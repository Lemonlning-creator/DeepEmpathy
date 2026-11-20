import pytest

from deep_empathy.config import Settings
from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import Analysis, Psychology, Reply, Review, SupportPlan
from deep_empathy.planning.service import plan_support
from deep_empathy.safety.service import reviewed_reply


class ProposedPlan:
    async def generate(self, task, data, schema, usage):
        return SupportPlan(
            goal="陪伴",
            validation="倾听",
            user_perspective="想被听见",
            agent_constraints=["尊重自主"],
            style="温和",
            ask_clarification=True,
            offer_advice=True,
            avoid_assertions=[],
        )


@pytest.mark.asyncio
async def test_listen_and_consecutive_question_limits_are_enforced():
    analysis = Analysis(emotion="累", event="当前表达", psychology=Psychology(), support_preference="listen")
    plan = await plan_support(ProposedPlan(), {}, analysis, Settings(), 0, [])
    assert not plan.ask_clarification and not plan.offer_advice
    analysis.support_preference = "unknown"
    plan = await plan_support(ProposedPlan(), {}, analysis, Settings(), 2, [])
    assert not plan.ask_clarification
    analysis.risk = "urgent"
    plan = await plan_support(ProposedPlan(), {}, analysis, Settings(), 0, [])
    assert "安全" in plan.goal and not plan.ask_clarification


@pytest.mark.asyncio
async def test_failed_review_has_one_revision_then_error():
    class Rejecting:
        def __init__(self):
            self.tasks = []

        async def generate(self, task, data, schema, usage):
            self.tasks.append(task)
            return (
                Reply(text="不适切内容")
                if task == "generation"
                else Review(passed=False, issues=["无依据断言"])
            )

    gateway = Rejecting()
    plan = await ProposedPlan().generate("", {}, None, [])
    with pytest.raises(AppError) as error:
        await reviewed_reply(gateway, {}, plan, [])
    assert error.value.code == "REPLY_REVIEW_FAILED"
    assert gateway.tasks == ["generation", "review", "generation", "review"]


@pytest.mark.asyncio
async def test_review_cannot_override_question_budget():
    class TooManyQuestions:
        async def generate(self, task, data, schema, usage):
            return Reply(text="你难过吗？要建议吗？") if task == "generation" else Review(passed=True)

    plan = await ProposedPlan().generate("", {}, None, [])
    with pytest.raises(AppError):
        await reviewed_reply(TooManyQuestions(), {}, plan, [])
