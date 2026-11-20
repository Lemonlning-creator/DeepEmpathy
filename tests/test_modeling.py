import asyncio

import pytest

from deep_empathy.domain.models import Citation, ClaimProposal
from deep_empathy.orchestration.service import UserLocks
from deep_empathy.user_model.profile import prepare_claims, valid_citations


def test_fake_and_assistant_citations_rejected():
    messages = [
        {"id": "1", "role": "user", "content": "我只是累了", "session_id": "a"},
        {"id": "2", "role": "assistant", "content": "你很内向", "session_id": "a"},
    ]
    assert not valid_citations([Citation(message_id="2", quote="你很内向")], messages)
    proposal = ClaimProposal(
        layer="behavior", statement="喜欢旅行", citations=[Citation(message_id="1", quote="喜欢旅行")]
    )
    prepared, discarded = prepare_claims([proposal], messages, [])
    assert prepared == [] and discarded == 1


def test_deep_claim_requires_longitudinal_evidence():
    messages = [
        {"id": str(i), "role": "user", "content": "我很在意自主选择", "session_id": "a" if i < 2 else "b"}
        for i in range(3)
    ]
    citations = [Citation(message_id=m["id"], quote=m["content"]) for m in messages]
    one = ClaimProposal(layer="core", statement="重视自主选择", citations=citations[:1])
    assert prepare_claims([one], messages, [])[0] == []
    many = one.model_copy(update={"citations": citations})
    assert len(prepare_claims([many], messages, [])[0]) == 1


@pytest.mark.asyncio
async def test_user_mutations_are_serialized_and_locks_released():
    locks, sequence = UserLocks(), []

    async def work(n):
        async with locks.hold("owner"):
            sequence.append(("start", n))
            await asyncio.sleep(0.001)
            sequence.append(("end", n))

    await asyncio.gather(*(work(i) for i in range(3)))
    assert sequence == [("start", 0), ("end", 0), ("start", 1), ("end", 1), ("start", 2), ("end", 2)]
    assert not locks.entries
