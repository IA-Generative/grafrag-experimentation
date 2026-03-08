from pydantic import BaseModel, Field


class PrincipalGrant(BaseModel):
    principal_type: str = Field(description="group or user")
    principal_value: str


class CorpusSourceDefinition(BaseModel):
    id: str
    source_kind: str
    source_name: str
    config: dict[str, str] = Field(default_factory=dict)


class CorpusVersionSummary(BaseModel):
    id: str
    label: str
    status: str
    document_count: int = 0
    snapshot_bytes: int = 0
    created_at: str
    published_at: str | None = None
    is_active: bool = False
    metrics: dict[str, object] = Field(default_factory=dict)


class JobSummary(BaseModel):
    id: str
    corpus_id: str
    version_id: str | None = None
    job_type: str
    status: str
    phase: str
    progress_percent: float = 0.0
    requested_by: str = ""
    retry_of_job_id: str | None = None
    error_category: str | None = None
    error_summary: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str
    logs_url: str | None = None


class CorpusSummary(BaseModel):
    id: str
    slug: str
    name: str
    description: str = ""
    workflow_state: str
    active_version_id: str | None = None
    active_version_label: str | None = None
    last_job: JobSummary | None = None
    allowed_groups: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)
    document_count: int = 0
    created_at: str
    updated_at: str


class CorpusDetail(CorpusSummary):
    sources: list[CorpusSourceDefinition] = Field(default_factory=list)
    versions: list[CorpusVersionSummary] = Field(default_factory=list)
    jobs: list[JobSummary] = Field(default_factory=list)


class NotificationItem(BaseModel):
    corpus_id: str
    corpus_name: str
    job_id: str
    level: str
    title: str
    message: str
    created_at: str
    link_url: str | None = None


class CreateCorpusRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=120)
    description: str = ""
    source_kind: str = Field(default="filesystem")
    source_name: str = Field(default="Primary source")
    source_config: dict[str, str] = Field(default_factory=dict)
    allowed_groups: list[str] = Field(default_factory=list)
    allowed_users: list[str] = Field(default_factory=list)


class QueueJobRequest(BaseModel):
    version_id: str | None = None


class ActionResponse(BaseModel):
    status: str
    details: str
    job: JobSummary | None = None
    version: CorpusVersionSummary | None = None


class MeResponse(BaseModel):
    email: str
    preferred_username: str
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    is_admin: bool = False


class CorpusManagerConfigResponse(BaseModel):
    auth_required: bool
    keycloak_url: str
    keycloak_js_url: str
    realm: str
    client_id: str
    openwebui_url: str
    corpus_manager_url: str
