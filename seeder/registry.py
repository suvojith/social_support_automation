"""Seed the citizen registry: profiles into PostgreSQL, documents into MongoDB.

Also drops a browsable copy of every document under data/samples/ so reviewers
can open them or upload them manually through the UI.

Usage: python -m seeder.registry
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.registry import CITIZENS, build_documents, get_profile_payload
from src.storage.mongo import MongoStore
from src.storage.postgres import PostgresClient

SAMPLES_DIR = Path("data/samples")


def seed_registry(pg: PostgresClient | None = None, mongo: MongoStore | None = None, write_files: bool = True):
    own_pg = pg is None
    own_mongo = mongo is None
    pg = pg or PostgresClient()
    mongo = mongo or MongoStore()

    pg.init_schema()
    print(f"[registry] Seeding {len(CITIZENS)} citizens...")
    for citizen in CITIZENS:
        profile = get_profile_payload(citizen)
        pg.upsert_citizen(profile)

        folder = SAMPLES_DIR / citizen["name"].replace(" ", "_")
        if write_files:
            folder.mkdir(parents=True, exist_ok=True)
        for doc in build_documents(citizen):
            mongo.save_registry_document(
                emirates_id=citizen["emirates_id"],
                doc_type=doc["doc_type"],
                filename=doc["filename"],
                content=doc["content"],
            )
            if write_files:
                (folder / doc["filename"]).write_bytes(doc["content"])
        print(f"[registry]   {citizen['name']} ({citizen['emirates_id']}) — 5 documents")

    print(f"[registry] Done. Profiles in PostgreSQL, documents in MongoDB + {SAMPLES_DIR}/")
    if own_pg:
        pg.close()
    if own_mongo:
        mongo.close()


if __name__ == "__main__":
    seed_registry()
