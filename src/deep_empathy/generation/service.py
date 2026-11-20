from deep_empathy.domain.models import Reply


async def generate_reply(gateway, payload, usage):
    return await gateway.generate("generation", payload, Reply, usage)
