import json
import logging
from pathlib import Path

from fastapi import Body, Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from auth import get_graph_viewer_auth
from config import get_settings
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
    source_prefix: str = Query(default=""),
    max_nodes: int = Query(default=80, ge=10, le=200),
    min_weight: float = Query(default=1.0, ge=0.0, le=100.0),
    _: dict[str, object] | None = Depends(graph_viewer_auth.require_viewer_token),
) -> GraphDataResponse:
    return service.graph_data(
        query=query,
        source_prefix=source_prefix,
        max_nodes=max_nodes,
        min_weight=min_weight,
    )


@app.get("/graph/raw", tags=["graph"])
def graph_raw(
    query: str = Query(default=""),
    source_prefix: str = Query(default=""),
    max_nodes: int = Query(default=80, ge=10, le=200),
    min_weight: float = Query(default=1.0, ge=0.0, le=100.0),
    _: dict[str, object] | None = Depends(graph_viewer_auth.require_viewer_token),
) -> Response:
    graphml_path = settings.graphrag_output_dir / "graph.graphml"
    if not graphml_path.exists():
        payload = service.graph_data(
            query=query,
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
def query(request: QueryRequest) -> QueryResponse:
    return service.query(request)


@app.post("/index", response_model=IndexResponse, tags=["index"])
def index(request: IndexRequest = Body(default_factory=IndexRequest)) -> IndexResponse:
    return service.index(request)
