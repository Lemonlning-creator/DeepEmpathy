"""Cheap, explicit heuristics, not a claim of semantic risk detection."""

import re

URGENT = re.compile(r"自杀|自残|不想活|想死|结束生命|伤害自己|杀人|suicid|kill myself", re.I)
COMPLEX = re.compile(
    r"帮我分析|分析一下|深入聊|深入分析|为什么我总是|理不清|两难|该不该|怎么选择|矛盾|deep analysis", re.I
)
SALIENT = re.compile(
    r"我喜欢|我不喜欢|我习惯|我的工作|我是[一名个]|我更希望|我希望你|以后请|其实我|理解错|纠正|记住"
)


def route(content, requested="auto"):
    if URGENT.search(content):
        return {"path": "deep", "reason": "risk_signal", "urgent": True}
    if requested == "deep":
        return {"path": "deep", "reason": "user_requested", "urgent": False}
    if requested != "fast" and (len(content) > 600 or COMPLEX.search(content)):
        return {"path": "deep", "reason": "complex_input", "urgent": False}
    return {"path": "fast", "reason": "ordinary", "urgent": False}


def modeling_reasons(content, completed_turns, interval):
    reasons = []
    if SALIENT.search(content):
        reasons.append("new_information_or_correction")
    if completed_turns % interval == 0:
        reasons.append("periodic_consolidation")
    return reasons
