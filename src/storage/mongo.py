"""MongoDB client: raw documents, extracted JSON, and GridFS for raw images.

Field-level encryption on extracted PII is applied BEFORE persistence (see src/governance/pii.py).
"""

from __future__ import annotations

import uuid
from typing import Any

from pymongo import MongoClient

from src.config.settings import get_settings

COLLECTION_RAW_DOCS = "raw_documents"
COLLECTION_EXTRACTED = "extracted_data"
COLLECTION_REGISTRY_DOCS = "registry_documents"


class MongoStore:
    def __init__(self, uri: str | None = None, db_name: str | None = None):
        s = get_settings()
        self.client = MongoClient(uri or s.mongo_uri)
        self.db = self.client[db_name or s.mongo_db]
        self.raw_docs = self.db[COLLECTION_RAW_DOCS]
        self.extracted = self.db[COLLECTION_EXTRACTED]
        self.registry_docs = self.db[COLLECTION_REGISTRY_DOCS]
        self.gridfs = self.db.fs  # GridFS bucket prefix
        self._ensure_indexes()

    def _ensure_indexes(self):
        self.raw_docs.create_index("application_id")
        self.raw_docs.create_index([("application_id", 1), ("doc_type", 1)])
        self.extracted.create_index("application_id")
        self.registry_docs.create_index([("emirates_id", 1), ("doc_type", 1)], unique=True)

    def save_raw_document(
        self,
        application_id: str,
        doc_type: str,
        content_bytes: bytes | None = None,
        metadata: dict | None = None,
        filename: str | None = None,
    ) -> str:
        """Persist a raw uploaded document. Images go to GridFS; text/PDF metadata stays inline."""
        doc_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "_id": doc_id,
            "application_id": application_id,
            "doc_type": doc_type,
            "filename": filename,
            "metadata": metadata or {},
        }
        if content_bytes and doc_type in ("emirates_id", "handwritten_form"):
            # Raw images live in GridFS
            fs_id = self.db.fs.files.insert_one({"filename": filename or f"{application_id}_{doc_type}", "application_id": application_id})
            self.db.fs.chunks.insert_one({"files_id": fs_id.inserted_id, "n": 0, "data": content_bytes})
            record["gridfs_id"] = str(fs_id.inserted_id)
        elif content_bytes:
            record["content"] = content_bytes.decode("utf-8", errors="replace")
        self.raw_docs.insert_one(record)
        return doc_id

    def get_raw_document(self, doc_id: str) -> dict | None:
        return self.raw_docs.find_one({"_id": doc_id})

    def list_raw_documents(self, application_id: str) -> list[dict]:
        return list(self.raw_docs.find({"application_id": application_id}))

    def save_extracted(self, application_id: str, doc_type: str, extracted: dict) -> str:
        record = {
            "application_id": application_id,
            "doc_type": doc_type,
            "data": extracted,
        }
        result = self.extracted.insert_one(record)
        return str(result.inserted_id)

    def get_extracted(self, application_id: str) -> list[dict]:
        return list(self.extracted.find({"application_id": application_id}))

    def save_registry_document(self, emirates_id: str, doc_type: str, filename: str, content: bytes):
        """Upsert one of a registry citizen's documents (bytes stored inline)."""
        self.registry_docs.replace_one(
            {"emirates_id": emirates_id, "doc_type": doc_type},
            {
                "emirates_id": emirates_id,
                "doc_type": doc_type,
                "filename": filename,
                "content": content,
            },
            upsert=True,
        )

    def get_registry_documents(self, emirates_id: str) -> list[dict]:
        return list(self.registry_docs.find({"emirates_id": emirates_id}))

    def close(self):
        self.client.close()
