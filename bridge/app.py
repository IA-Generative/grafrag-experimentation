import json
import logging
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from auth import (
    AuthenticatedUser,
    BEARER_SCHEME,
    get_graph_viewer_auth,
    get_keycloak_token_validator,
)
from config import get_settings
from corpus_service import CorpusManagerService
from models import (
    GraphDataResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    QueryRequest,
    QueryResponse,
)
from service import GraphRAGService

settings = get_settings()
GRAPH_VIEW_PATH = Path(__file__).with_name("graph_view.html")
ASSET_DIR = Path(__file__).with_name("assets")
ASSET_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

service = GraphRAGService(settings)
graph_viewer_auth = get_graph_viewer_auth()
token_validator = get_keycloak_token_validator()
corpus_manager = CorpusManagerService(settings)
app = FastAPI(title="GraphRAG Bridge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/assets", StaticFiles(directory=ASSET_DIR), name="assets")


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    return {"service": "graphrag-bridge", "status": "ok"}


@app.get("/healthz", response_model=HealthResponse, tags=["meta"])
def healthz() -> HealthResponse:
    return service.health()


@app.get("/config", tags=["meta"])
def config() -> dict[str, object]:
    return service.config_snapshot()


@app.get("/graph", response_class=HTMLResponse, tags=["graph"])
def graph_view() -> str:
    html = GRAPH_VIEW_PATH.read_text(encoding="utf-8")
    return html.replace(
        "__GRAPH_VIEWER_CONFIG__",
        json.dumps(graph_viewer_auth.viewer_config()),
    )


@app.get("/graph/config", tags=["graph"])
def graph_config() -> dict[str, object]:
    return graph_viewer_auth.viewer_config()


@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(ASSET_DIR / "favicon.ico", media_type="image/x-icon")


@app.get("/graph/data", response_model=GraphDataResponse, tags=["graph"])
def graph_data(
    query: str = Query(default=""),
    corpus_id: str = Query(default=""),
    source_prefix: str = Query(default=""),
    max_nodes: int = Query(default=80, ge=10, le=200),
    min_weight: float = Query(default=1.0, ge=0.0, le=100.0),
    viewer_payload: dict[str, object] | None = Depends(graph_viewer_auth.require_viewer_token),
) -> GraphDataResponse:
    active_service = service
    if corpus_id.strip():
        user = _query_user_from_sources(None, viewer_payload)
        if user is None:
            raise HTTPException(status_code=401, detail="Viewer authentication is required.")
        try:
            active_service, _ = corpus_manager.resolve_query_service(corpus_id.strip(), user)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Corpus not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return active_service.graph_data(
        query=query,
        corpus_id=corpus_id,
        source_prefix=source_prefix,
        max_nodes=max_nodes,
        min_weight=min_weight,
    )


@app.get("/graph/raw", tags=["graph"])
def graph_raw(
    query: str = Query(default=""),
    corpus_id: str = Query(default=""),
    source_prefix: str = Query(default=""),
    max_nodes: int = Query(default=80, ge=10, le=200),
    min_weight: float = Query(default=1.0, ge=0.0, le=100.0),
    viewer_payload: dict[str, object] | None = Depends(graph_viewer_auth.require_viewer_token),
) -> Response:
    active_service = service
    active_settings = settings
    if corpus_id.strip():
        user = _query_user_from_sources(None, viewer_payload)
        if user is None:
            raise HTTPException(status_code=401, detail="Viewer authentication is required.")
        try:
            active_service, _ = corpus_manager.resolve_query_service(corpus_id.strip(), user)
            active_settings = active_service.settings
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Corpus not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    graphml_path = active_settings.graphrag_output_dir / "graph.graphml"
    if not graphml_path.exists():
        payload = active_service.graph_data(
            query=query,
            corpus_id=corpus_id,
            source_prefix=source_prefix,
            max_nodes=max_nodes,
            min_weight=min_weight,
        )
        return Response(
            content=payload.model_dump_json(indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="graphe-documentaire.json"'
            },
        )
    return FileResponse(
        graphml_path,
        media_type="application/graphml+xml",
        filename="graphe.graphml",
    )


@app.post("/query", response_model=QueryResponse, tags=["query"])
def query(
    request: QueryRequest,
    credentials=Depends(BEARER_SCHEME),
) -> QueryResponse:
    user = _query_user_from_sources(request, token_validator.optional_payload(credentials))
    active_service = service

    if user is not None and not request.corpus_id:
        request.corpus_id = corpus_manager.resolve_default_corpus(user)

    if request.corpus_id:
        if user is None:
            raise HTTPException(
                status_code=401,
                detail="A trusted user context is required to query a protected corpus.",
            )
        try:
            active_service, _ = corpus_manager.resolve_query_service(request.corpus_id, user)
        except LookupError as error:
            raise HTTPException(status_code=404, detail="Corpus not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    notices = []
    if user is not None:
        notices = [item.model_dump() for item in corpus_manager.notifications(user, request.corpus_id)]

    return active_service.query(request, notices=notices)


@app.post("/index", response_model=IndexResponse, tags=["index"])
def index(request: IndexRequest = Body(default_factory=IndexRequest)) -> IndexResponse:
    return service.index(request)


def _query_user_from_sources(
    request: QueryRequest | None,
    payload: dict[str, object] | None,
) -> AuthenticatedUser | None:
    if payload:
        return token_validator.user_from_payload(payload)
    if request is None:
        return None
    if not request.user_email and not request.user_groups and not request.user_roles:
        return None
    return AuthenticatedUser(
        sub=request.user_email or "openwebui-user",
        email=request.user_email or "",
        preferred_username=request.user_email or "openwebui-user",
        groups=list(request.user_groups),
        roles=list(request.user_roles),
        raw_payload={},
    )
