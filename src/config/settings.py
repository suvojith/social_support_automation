"""Centralized settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Profile
    profile: Literal["local", "cloud"] = "local"
    llm_model: str = "qwen3.5:9b-mlx"
    embed_model: str = "bge-m3"
    ollama_host: str = "http://host.docker.internal:11434"

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "sswa"
    postgres_password: str = "change_me_in_prod"
    postgres_db: str = "sswa"

    # MongoDB
    mongo_host: str = "mongo"
    mongo_port: int = 27017
    mongo_user: str = "sswa"
    mongo_password: str = "change_me_in_prod"
    mongo_db: str = "sswa"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333

    # Neo4j
    neo4j_host: str = "neo4j"
    neo4j_port: int = 7687
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change_me_in_prod"

    # Langfuse
    langfuse_host: str = "http://langfuse:3000"
    langfuse_public_key: str = "pk-lf-sswa-demo"
    langfuse_secret_key: str = "sk-lf-sswa-demo"

    # API auth
    api_username: str = "reviewer"
    api_password: str = "change_me_in_prod"
    basic_auth_realm: str = "SSWA Demo"

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    ui_port: int = 8501
    environment: str = "development"
    log_level: str = "INFO"

    # Synthetic data
    n_synthetic_applicants: int = 200
    label_noise_rate: float = 0.12
    random_seed: int = 42

    # PG DSN
    @property
    def pg_dsn(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def mongo_uri(self) -> str:
        return f"mongodb://{self.mongo_user}:{self.mongo_password}@{self.mongo_host}:{self.mongo_port}/?authSource=admin"

    @property
    def neo4j_uri(self) -> str:
        return f"bolt://{self.neo4j_host}:{self.neo4j_port}"

    @property
    def qdrant_url(self) -> str:
        return f"http://{self.qdrant_host}:{self.qdrant_port}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
