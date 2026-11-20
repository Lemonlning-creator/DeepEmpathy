"""Mem0 OSS adapter. All inference/embeddings are cloud configured, never local models."""
import asyncio
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse


def result_rows(value):
    return value.get("results", []) if isinstance(value, dict) else value


class Mem0Store:
    def __init__(self, settings):
        self.settings = settings
        self.memory = None
        self.gate = asyncio.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mem0")
        self.tasks = set()

    def _memory(self):
        if self.memory is not None:
            return self.memory
        s = self.settings
        endpoint = urlparse(s.embedding_base_url)
        if endpoint.scheme != "https" or not endpoint.hostname or endpoint.query or endpoint.fragment:
            raise ValueError("Cloud embeddings require an HTTPS base URL without query or fragment")
        root = Path(s.memory_path).resolve()
        root.mkdir(parents=True, exist_ok=True)
        os.environ["MEM0_DIR"] = str(root / "runtime")
        os.environ["MEM0_TELEMETRY"] = "false"
        from mem0 import Memory

        fingerprint = hashlib.sha256(f"{s.embedding_base_url}:{s.embedding_model}:{s.embedding_dims}".encode()).hexdigest()[:12]
        manifest = root / "embedding.json"
        if manifest.exists() and json.loads(manifest.read_text()).get("fingerprint") != fingerprint:
            raise ValueError("Embedding config changed: use a new MEMORY_PATH to rebuild the index")
        if not manifest.exists():
            manifest.write_text(json.dumps({"fingerprint": fingerprint}))
        self.memory = Memory.from_config({
            "version": "v1.1",
            # App SQLite owns durable provenance; do not persist a second copy of deleted facts.
            "history_db_path": ":memory:",
            "vector_store": {"provider": "qdrant", "config": {
                "path": str(root / "vectors"), "collection_name": f"deep_empathy_{fingerprint}",
                "embedding_model_dims": s.embedding_dims,
            }},
            "llm": {"provider": "openai", "config": {
                "model": s.llm_model, "api_key": s.llm_api_key, "openai_base_url": s.llm_base_url,
            }},
            "embedder": {"provider": "openai", "config": {
                "model": s.embedding_model, "api_key": s.embedding_api_key,
                "openai_base_url": s.embedding_base_url, "embedding_dims": s.embedding_dims,
            }},
        })
        # No SDK retry storm or unbounded network wait. infer=False bypasses Mem0's LLM extraction.
        client = self.memory.embedding_model.client
        client.timeout, client.max_retries = 8, 0
        return self.memory

    async def _call(self, fn):
        async def run():
            async with self.gate:
                return await asyncio.get_running_loop().run_in_executor(self.pool, fn)
        task = asyncio.create_task(run())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        # A timed-out caller must not release the vector-store gate while its SDK thread is running.
        return await asyncio.shield(task)

    async def upsert(self, owner, document, revision):
        def write():
            m = self._memory()
            meta = {**document["metadata"], "document_id": document["id"],
                    "source_hash": document["hash"], "revision": revision}
            existing = result_rows(m.get_all(user_id=owner, filters={
                "document_id": document["id"], "source_hash": document["hash"], "revision": revision,
            }, limit=10))
            if existing:
                return existing[0]["id"]
            result = m.add(document["text"], user_id=owner, metadata=meta, infer=False)
            return result_rows(result)[0]["id"]
        return await self._call(write)

    async def search(self, owner, query, revision, limit):
        # Indexing never forces foreground chat to queue behind cloud embedding writes.
        if self.gate.locked():
            return None
        return await self._call(lambda: result_rows(self._memory().search(
            query, user_id=owner, filters={"revision": revision}, limit=limit, rerank=False,
        )))

    def _delete(self, memory_id):
        m = self._memory()
        if m.get(memory_id) is not None:
            m.delete(memory_id)
        # Mem0 1.0.11 retains deleted values in its audit log; ours is transient and purged too.
        m.db.connection.execute("DELETE FROM history WHERE memory_id=?", (memory_id,))
        m.db.connection.commit()

    async def delete(self, memory_id):
        return await self._call(lambda: self._delete(memory_id))

    async def purge(self, owner):
        def purge():
            m = self._memory()
            while True:
                rows = result_rows(m.get_all(user_id=owner, limit=100))
                if not rows:
                    return
                for row in rows:
                    self._delete(row["id"])
        await self._call(purge)

    async def close(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        if self.memory:
            def close():
                self.memory.close()
                self.memory.vector_store.client.close()
                self.memory.embedding_model.client.close()
                self.memory.llm.client.close()
            await asyncio.get_running_loop().run_in_executor(self.pool, close)
        self.pool.shutdown(wait=False)
