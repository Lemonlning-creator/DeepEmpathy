from deep_empathy.domain.models import Analysis, Psychology
from deep_empathy.user_model.profile import valid_citations


async def perceive(gateway, data, observations, usage):
    """One cloud call combines event perception and situation-dependent psychology."""
    result = await gateway.generate("analysis", data, Analysis, usage)
    citations = valid_citations(result.psychology.citations, observations)
    if len(citations) != len(result.psychology.citations) or not citations:
        result.psychology = Psychology()
    return result
