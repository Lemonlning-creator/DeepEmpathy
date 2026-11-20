"""Explicit scenario baseline, never disguised as observed conversation evidence."""
from hashlib import sha256

from deep_empathy.storage.repository import invalidate_memory, now, uid


def initialize_profile(repo, owner, seed):
    if not seed or not repo.user(owner)["memory"]:
        return False
    seed_id = seed["id"]
    with repo.connect() as db:
        inserted = db.execute(
            "INSERT OR IGNORE INTO profile_initializations(user_id,seed_id,created_at) VALUES(?,?,?)",
            (owner, seed_id, now()),
        ).rowcount
        if not inserted:
            return False
        # Retire only the former imported baseline; preserve real conversations and later claims.
        for previous in seed.get("supersedes", []):
            old_sid = sha256(f"initial:{owner}:{previous}".encode()).hexdigest()[:32]
            db.execute(
                "UPDATE claims SET status='superseded',version=version+1,updated_at=? "
                "WHERE user_id=? AND session_id=? AND status NOT IN ('retracted','contradicted','user_confirmed') "
                "AND id IN (SELECT claim_id FROM evidence WHERE source_type='initial_profile')",
                (now(), owner, old_sid),
            )
        db.execute("UPDATE turns SET trace='{}' WHERE user_id=?", (owner,))
        sid = sha256(f"initial:{owner}:{seed_id}".encode()).hexdigest()[:32]
        stamp = now()
        db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                   (sid, owner, f"初始画像 · {seed['name']}", "cloud", stamp, stamp))
        for layer, statements in seed["layers"].items():
            if layer not in {"core", "regulation", "cognition", "identity", "behavior"}:
                raise ValueError("Unknown initial profile layer")
            for item in statements:
                statement = item["statement"] if isinstance(item, dict) else item
                epistemic = item.get("epistemic", "known") if isinstance(item, dict) else "known"
                tentative = epistemic == "tentative"
                confidence = {"tentative": .35, "observed": .65, "known": .8}[epistemic]
                cid = uid()
                db.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (cid, owner, sid, layer, statement, "tentative" if tentative else "supported",
                            int(not tentative), confidence, 1, None, stamp, stamp))
                db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?)",
                           (uid(), owner, cid, None, statement, None, None, "initial_profile"))
        # Discard pending modeling based on the former empty/partial baseline.
        invalidate_memory(db, owner)
    return True
