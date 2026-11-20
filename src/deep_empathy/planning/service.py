from deep_empathy.domain.models import SupportPlan


async def plan_support(gateway, data, analysis, settings, consecutive, usage):
    maximum = settings.defe.get("interaction", {}).get("max_consecutive_clarifying_turns", 2)
    allowed = consecutive < maximum and analysis.support_preference != "listen" and analysis.risk != "urgent"
    result = await gateway.generate(
        "planning",
        {
            **data,
            "analysis": analysis.model_dump(),
            "persona": settings.persona,
            "mode": "prompt_guided",
            "uncertainty_method": "heuristic",
            "clarification_allowed": allowed,
            "advice_allowed": analysis.support_preference == "advice",
            "max_questions": 1,
        },
        SupportPlan,
        usage,
    )
    # Enforce gates after model output as well as in the prompt.
    result.ask_clarification = result.ask_clarification and allowed
    result.offer_advice = result.offer_advice and analysis.support_preference == "advice"
    if analysis.risk == "urgent":
        result.goal = "优先眼前安全，鼓励联系现实中可信的人或当地紧急服务"
        result.ask_clarification = False
        result.offer_advice = False
    return result
