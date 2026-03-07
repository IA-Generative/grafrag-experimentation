import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_VALUES = {"", "CHANGE_ME", "EXAMPLE_ONLY", "REPLACE_ME"}
DEFAULT_EMBEDDING_VECTOR_SIZE = 3584
EMBEDDING_VECTOR_SIZES = {
    "bge-multilingual-gemma2": 3584,
    "qwen3-embedding-8b": 4096,
}


class Settings(BaseSettings):
    bridge_host: str = Field(default="0.0.0.0", validation_alias="BRIDGE_HOST")
    bridge_port: int = Field(default=8081, validation_alias="BRIDGE_PORT")
    bridge_public_url: str = Field(
        default="http://localhost:8081", validation_alias="BRIDGE_PUBLIC_URL"
    )
    openwebui_public_url: str = Field(
        default="http://localhost:3000", validation_alias="OPENWEBUI_PUBLIC_URL"
    )
    keycloak_public_url: str = Field(
        default="http://localhost:8082", validation_alias="KEYCLOAK_PUBLIC_URL"
    )
    keycloak_internal_url: str = Field(
        default="http://keycloak:8080", validation_alias="KEYCLOAK_INTERNAL_URL"
    )
    keycloak_realm: str = Field(default="openwebui", validation_alias="KEYCLOAK_REALM")
    graph_viewer_client_id: str = Field(
        default="graphrag-viewer", validation_alias="GRAPH_VIEWER_CLIENT_ID"
    )
    graph_viewer_auth_required: bool = Field(
        default=True, validation_alias="GRAPH_VIEWER_AUTH_REQUIRED"
    )
    openai_api_base: str = Field(
        default="https://api.scaleway.ai/a9158aac-8404-46ea-8bf5-1ca048cd6ab4/v1",
        validation_alias="OPENAI_API_BASE",
    )
    openai_api_key: str = Field(
        default="CHANGE_ME",
        validation_alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(
        default="mistral-small-3.2-24b-instruct-2506",
        validation_alias="OPENAI_MODEL",
    )
    openai_embedding_model: str = Field(
        default="bge-multilingual-gemma2", validation_alias="OPENAI_EMBEDDING_MODEL"
    )
    openai_embedding_vector_size: int = Field(
        default=DEFAULT_EMBEDDING_VECTOR_SIZE,
        validation_alias="OPENAI_EMBEDDING_VECTOR_SIZE",
    )
    graphrag_root: Path = Field(
        default=Path("/app/graphrag"), validation_alias="GRAPHRAG_ROOT"
    )
    graphrag_input_dir: Path = Field(
        default=Path("/app/graphrag/input"), validation_alias="GRAPHRAG_INPUT_DIR"
    )
    graphrag_output_dir: Path = Field(
        default=Path("/app/graphrag/output"), validation_alias="GRAPHRAG_OUTPUT_DIR"
    )
    graphrag_cache_dir_override: Path | None = Field(
        default=None, validation_alias="GRAPHRAG_CACHE_DIR"
    )
    graphrag_method: str = Field(default="local", validation_alias="GRAPHRAG_METHOD")
    graphrag_response_type: str = Field(
        default="Multiple Paragraphs", validation_alias="GRAPHRAG_RESPONSE_TYPE"
    )
    graphrag_top_k: int = Field(default=4, validation_alias="GRAPHRAG_TOP_K")
    graphrag_cache_s3_enabled: bool = Field(
        default=False, validation_alias="GRAPHRAG_CACHE_S3_ENABLED"
    )
    graphrag_cache_s3_bucket: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_BUCKET"
    )
    graphrag_cache_s3_prefix: str = Field(
        default="graphrag/cache", validation_alias="GRAPHRAG_CACHE_S3_PREFIX"
    )
    graphrag_cache_s3_region: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_REGION"
    )
    graphrag_cache_s3_endpoint_url: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_ENDPOINT_URL"
    )
    graphrag_cache_s3_access_key_id: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_ACCESS_KEY_ID"
    )
    graphrag_cache_s3_secret_access_key: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_SECRET_ACCESS_KEY"
    )
    graphrag_cache_s3_session_token: str = Field(
        default="", validation_alias="GRAPHRAG_CACHE_S3_SESSION_TOKEN"
    )
    request_timeout_seconds: int = Field(
        default=55, validation_alias="REQUEST_TIMEOUT_SECONDS"
    )
    graphrag_cli_timeout_seconds: int = Field(
        default=30, validation_alias="GRAPHRAG_CLI_TIMEOUT_SECONDS"
    )
    graphrag_index_timeout_seconds: int = Field(
        default=3600, validation_alias="GRAPHRAG_INDEX_TIMEOUT_SECONDS"
    )
    llm_timeout_seconds: int = Field(
        default=20, validation_alias="LLM_TIMEOUT_SECONDS"
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def __init__(self, **values: object) -> None:
        super().__init__(**values)
        if "openai_api_base" not in values and os.getenv("SCW_LLM_BASE_URL"):
            self.openai_api_base = os.environ["SCW_LLM_BASE_URL"]
        if "openai_api_key" not in values and os.getenv("SCW_SECRET_KEY_LLM"):
            self.openai_api_key = os.environ["SCW_SECRET_KEY_LLM"]
        if "openai_model" not in values and os.getenv("SCW_LLM_MODEL"):
            self.openai_model = os.environ["SCW_LLM_MODEL"]
        if not os.getenv("OPENAI_EMBEDDING_VECTOR_SIZE"):
            self.openai_embedding_vector_size = EMBEDDING_VECTOR_SIZES.get(
                self.openai_embedding_model,
                DEFAULT_EMBEDDING_VECTOR_SIZE,
            )

    @property
    def llm_ready(self) -> bool:
        return self.openai_api_key.strip() not in PLACEHOLDER_VALUES

    @property
    def graphrag_cache_dir(self) -> Path:
        if self.graphrag_cache_dir_override:
            return self.graphrag_cache_dir_override
        return self.graphrag_root / "cache"

    @property
    def graphrag_cache_s3_ready(self) -> bool:
        return (
            self.graphrag_cache_s3_enabled
            and self.graphrag_cache_s3_bucket.strip() not in PLACEHOLDER_VALUES
        )

    @property
    def chat_completions_url(self) -> str:
        base = self.openai_api_base.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    @property
    def keycloak_issuer(self) -> str:
        return f"{self.keycloak_public_url.rstrip('/')}/realms/{self.keycloak_realm}"

    @property
    def keycloak_jwks_url(self) -> str:
        return (
            f"{self.keycloak_internal_url.rstrip('/')}/realms/"
            f"{self.keycloak_realm}/protocol/openid-connect/certs"
        )

    @property
    def keycloak_js_url(self) -> str:
        return f"{self.keycloak_public_url.rstrip('/')}/js/keycloak.js"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
