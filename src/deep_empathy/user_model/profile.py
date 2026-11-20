"""Evidence gates are ordinary code, independent of the model's confidence."""

from deep_empathy.storage.repository import now, uid


def valid_citations(citations, messages):
    by_id = {m["id"]: m for m in messages if m["role"] == "user"}
    found, seen = [], set()
    for citation in citations:
        message = by_id.get(citation.message_id)
        key = (citation.message_id, citation.quote)
        if message and citation.quote in message["content"] and key not in seen:
            start = message["content"].index(citation.quote)
            found.append(
                {
                    "message_id": message["id"],
                    "quote": citation.quote,
                    "start": start,
                    "end": start + len(citation.quote),
                    "source_type": "user_message",
                }
            )
            seen.add(key)
    return found


def prepare_claims(proposals, messages, existing):
    prepared, discarded = [], 0
    seen_proposals = set()
    by_id = {c["id"]: c for c in existing}
    by_message = {m["id"]: m for m in messages}
    for proposal in proposals:
        key = (proposal.layer, proposal.statement.strip())
        if key in seen_proposals:
            continue
        seen_proposals.add(key)
        evidence = valid_citations(proposal.citations, messages)
        if len(evidence) != len(proposal.citations):
            discarded += 1
            continue
        old = by_id.get(proposal.replaces_id)
        seed_correction = bool(
            old and proposal.explicit and evidence
            and any(e["source_type"] == "initial_profile" for e in old.get("evidence", []))
        )
        if proposal.layer in ("cognition", "regulation", "core") and not seed_correction:
            # Three observations in at least two sessions are required for stable deep claims.
            if (
                len({e["message_id"] for e in evidence}) < 3
                or len({by_message[e["message_id"]]["session_id"] for e in evidence}) < 2
            ):
                discarded += 1
                continue
        if proposal.replaces_id and (not old or old["status"] == "user_confirmed"):
            discarded += 1
            continue
        duplicate = next(
            (
                c
                for c in existing
                if c["status"] != "superseded" and c["layer"] == proposal.layer
                and c["statement"].strip() == proposal.statement.strip()
            ),
            None,
        )
        if duplicate:
            if duplicate["status"] not in ("retracted", "contradicted"):
                old_keys = {(e["message_id"], e["quote"]) for e in duplicate["evidence"]}
                added = [e for e in evidence if (e["message_id"], e["quote"]) not in old_keys]
                if added:
                    prepared.append(
                        {
                            "id": duplicate["id"],
                            "merge_into": duplicate["id"],
                            "evidence": added,
                            "statement": duplicate["statement"],
                            "layer": duplicate["layer"],
                        }
                    )
            continue
        if any(c["statement"] == proposal.statement and c["layer"] == proposal.layer for c in prepared):
            continue
        prepared.append(
            {
                "id": uid(),
                "layer": proposal.layer,
                "statement": proposal.statement,
                "explicit": int(proposal.explicit),
                "evidence": evidence,
                "status": "tentative",
                "confidence": 0.65 if proposal.explicit else 0.35,
                "supersedes_id": old["id"] if old else None,
            }
        )
    return prepared, discarded


def persist_claims(db, owner, session_id, claims):
    for c in claims:
        stamp = now()
        if c.get("merge_into"):
            db.execute(
                "UPDATE claims SET version=version+1,updated_at=? WHERE user_id=? AND id=?",
                (stamp, owner, c["id"]),
            )
        elif c["supersedes_id"]:
            db.execute(
                "UPDATE claims SET status='contradicted',version=version+1,updated_at=? "
                "WHERE user_id=? AND id=?",
                (stamp, owner, c["supersedes_id"]),
            )
        if not c.get("merge_into"):
            db.execute(
                "INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    c["id"],
                    owner,
                    session_id,
                    c["layer"],
                    c["statement"],
                    c["status"],
                    c["explicit"],
                    c["confidence"],
                    1,
                    c["supersedes_id"],
                    stamp,
                    stamp,
                ),
            )
        for e in c["evidence"]:
            db.execute(
                "INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)",
                (uid(), owner, c["id"], e["message_id"], e["quote"], e["start"], e["end"], e["source_type"]),
            )
        counts = db.execute(
            "SELECT COUNT(DISTINCT message_id),COUNT(DISTINCT m.session_id) "
            "FROM evidence e LEFT JOIN messages m ON m.id=e.message_id "
            "WHERE e.claim_id=? AND e.user_id=?",
            (c["id"], owner),
        ).fetchone()
        if counts[0] >= 3 and counts[1] >= 2:
            db.execute(
                "UPDATE claims SET status='supported',confidence=0.8 WHERE id=? AND user_id=? "
                "AND status='tentative'",
                (c["id"], owner),
            )
