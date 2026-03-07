from pydantic import BaseModel, Field


class Citation(BaseModel):
    path: str
    excerpt: str = ""


class GraphSourceOption(BaseModel):
    id: str
    label: str


class GraphFragment(BaseModel):
    id: str
    text: str
    token_count: int = 0
    document_paths: list[str] = Field(default_factory=list)


class GraphNode(BaseModel):
    id: str
    label: str
    entity_type: str = ""
    description: str = ""
    degree: int = 0
    frequency: int = 0
    size: float = 1.0
    source_group: str = ""
    document_paths: list[str] = Field(default_factory=list)
    fragments: list[GraphFragment] = Field(default_factory=list)


class GraphEdge(BaseModel):
    source: str
    target: str
    description: str = ""
    weight: float = 0.0
    document_paths: list[str] = Field(default_factory=list)
    fragments: list[GraphFragment] = Field(default_factory=list)


class GraphDataResponse(BaseModel):
    graph_ready: bool
    query: str = ""
    source_prefix: str = ""
    max_nodes: int
    min_weight: float
    total_nodes: int = 0
    total_edges: int = 0
    available_sources: list[GraphSourceOption] = Field(default_factory=list)
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    message: str = ""
    download_url: str = ""


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, description="User question sent by Open WebUI.")
    method: str | None = Field(
        default=None, description="GraphRAG query method, usually local or global."
    )
    response_type: str | None = Field(
        default=None, description="Requested answer style for GraphRAG."
    )
    top_k: int | None = Field(
        default=None, ge=1, le=20, description="Maximum number of corpus chunks to use."
    )


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    method: str
    engine_used: str
    warnings: list[str] = Field(default_factory=list)
    raw_output: str | None = None
    graph_url: str | None = None


class IndexRequest(BaseModel):
    rebuild: bool = Field(
        default=False, description="Whether to force a refresh of the local index metadata."
    )


class IndexResponse(BaseModel):
    status: str
    engine_used: str
    details: str


class HealthResponse(BaseModel):
    status: str
    graphrag_cli_available: bool
    index_present: bool
    graphrag_query_ready: bool
    llm_configured: bool
