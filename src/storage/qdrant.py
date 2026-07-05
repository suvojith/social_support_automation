"""Qdrant client: vector store for eligibility rules + enablement programs (RAG)."""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from src.config.settings import get_settings

COLLECTION_RULES = "eligibility_rules"
COLLECTION_PROGRAMS = "enablement_programs"
VECTOR_SIZE = 1024  # bge-m3 dimension


class QdrantStore:
    def __init__(self, url: str | None = None):
        s = get_settings()
        self.client = QdrantClient(url=url or s.qdrant_url)
        self._ensure_collections()

    def _ensure_collections(self):
        for name in (COLLECTION_RULES, COLLECTION_PROGRAMS):
            cols = [c.name for c in self.client.get_collections().collections]
            if name not in cols:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=qmodels.VectorParams(size=VECTOR_SIZE, distance=qmodels.Distance.COSINE),
                )

    def upsert_programs(self, programs: list[dict], embeddings: list[list[float]]):
        points = [
            qmodels.PointStruct(
                id=idx,
                vector=embeddings[idx],
                payload=programs[idx],
            )
            for idx in range(len(programs))
        ]
        self.client.upsert(collection_name=COLLECTION_PROGRAMS, points=points)

    def upsert_rules(self, rules: list[dict], embeddings: list[list[float]]):
        points = [qmodels.PointStruct(id=idx, vector=embeddings[idx], payload=rules[idx]) for idx in range(len(rules))]
        self.client.upsert(collection_name=COLLECTION_RULES, points=points)

    def search_programs(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        results = self.client.query_points(collection_name=COLLECTION_PROGRAMS, query=query_vector, limit=limit)
        return [p.payload for p in results.points]

    def search_rules(self, query_vector: list[float], limit: int = 3) -> list[dict]:
        results = self.client.query_points(collection_name=COLLECTION_RULES, query=query_vector, limit=limit)
        return [p.payload for p in results.points]

    def close(self):
        self.client.close()
