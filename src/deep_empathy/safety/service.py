from deep_empathy.domain.errors import AppError
from deep_empathy.domain.models import Review
from deep_empathy.generation.service import generate_reply


async def reviewed_reply(gateway, data, plan, usage):
    payload = {**data, "plan": plan.model_dump()}
    for revision in range(2):
        reply = await generate_reply(gateway, payload, usage)
        review = await gateway.generate("review", {**payload, "reply": reply.text}, Review, usage)
        # Additional deterministic constraint: at most one explicit question mark.
        questions = reply.text.count("？") + reply.text.count("?")
        if questions > (1 if plan.ask_clarification else 0):
            review.passed = False
            review.issues.append("问题数量超过本轮策略允许范围")
        if review.passed:
            return reply, revision
        payload["review_issues"] = review.issues
    raise AppError("REPLY_REVIEW_FAILED", "这次回复未通过表达检查，请稍后重试。", 502)
