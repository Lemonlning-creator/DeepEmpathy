import re


def build_context(repo, owner, session_id, content, memory_enabled, max_chars, mode, cutoff=None):
    recent = repo.messages(owner, session_id, limit=30, cutoff=cutoff)
    # Keep the current conversation intact within a strict character budget. No local embeddings.
    budget, selected = max_chars // 2, []
    for message in reversed(recent):
        if budget - len(message["content"]) < 0:
            break
        selected.append(message)
        budget -= len(message["content"])
    selected.reverse()
    claims, related, corrections = [], [], []
    if memory_enabled and mode == "cloud":
        # Demo and cloud histories remain separate even for the same local identity.
        candidates = repo.rows(
            "SELECT m.* FROM messages m JOIN sessions s ON s.id=m.session_id "
            "WHERE m.user_id=? AND m.session_id<>? AND m.role='user' AND s.mode='cloud' "
            "AND m.rowid<=? "
            "ORDER BY m.rowid DESC LIMIT 150",
            (owner, session_id, cutoff or 9223372036854775807),
        )
        terms = set(re.findall(r"[a-zA-Z]{2,}|[\u4e00-\u9fff]{2}", content))
        scored = sorted(candidates, key=lambda m: sum(t in m["content"] for t in terms), reverse=True)
        used = 0
        for m in scored:
            if any(t in m["content"] for t in terms) and used + len(m["content"]) < max_chars // 4:
                related.append(m)
                used += len(m["content"])
            if len(related) >= 8:
                break
        used = 0
        for c in repo.profile(owner, limit=64):
            size = len(c["statement"]) + sum(len(e["quote"]) for e in c["evidence"])
            if used + size > max_chars // 4:
                continue
            claims.append(c)
            used += size
        corrections = repo.rows(
            "SELECT id,statement,status FROM claims WHERE user_id=? "
            "AND status IN ('retracted','contradicted','user_confirmed') "
            "ORDER BY updated_at DESC LIMIT 20",
            (owner,),
        )
    summaries = repo.rows(
        "SELECT text,source_ids FROM summaries WHERE user_id=? AND session_id=?", (owner, session_id)
    )
    feedback = repo.rows(
        "SELECT f.rating,f.comment FROM feedback f JOIN turns t ON t.id=f.turn_id "
        "WHERE f.user_id=? AND t.session_id=? ORDER BY f.rowid DESC LIMIT 3",
        (owner, session_id),
    )
    return {
        "history": selected,
        "related_observations": related,
        "profile": claims,
        "user_corrections": corrections,
        "recent_feedback": feedback,
        "summary": summaries[0]["text"] if summaries else "",
    }
