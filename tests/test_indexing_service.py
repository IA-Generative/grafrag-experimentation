from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))

from config import Settings  # noqa: E402
from service import GraphRAGService, ScoredDocument  # noqa: E402
from models import IndexRequest, QueryRequest  # noqa: E402


def build_settings(tmp_path: Path) -> Settings:
    root = tmp_path / "graphrag"
    return Settings(
        GRAPHRAG_ROOT=root,
        GRAPHRAG_INPUT_DIR=root / "input",
        GRAPHRAG_OUTPUT_DIR=root / "output",
        GRAPHRAG_CACHE_DIR=root / "cache",
        GRAPH_VIEWER_AUTH_REQUIRED=False,
        REQUEST_TIMEOUT_SECONDS=120,
        GRAPHRAG_CLI_TIMEOUT_SECONDS=30,
        GRAPHRAG_GLOBAL_CLI_TIMEOUT_SECONDS=90,
        GRAPHRAG_INDEX_TIMEOUT_SECONDS=321,
        LLM_TIMEOUT_SECONDS=20,
    )


def test_index_uses_dedicated_graphrag_timeout(tmp_path, monkeypatch) -> None:
    service = GraphRAGService(build_settings(tmp_path))
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_graphrag_cli_available", lambda: True)
    monkeypatch.setattr(service, "_graphrag_query_artifacts_present", lambda: True)

    def fake_run(command: list[str], timeout_seconds: int | None = None):
        captured["command"] = command
        captured["timeout_seconds"] = timeout_seconds

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(service, "_run_command", fake_run)

    result = service.index(IndexRequest(rebuild=True))

    assert result.status == "ok"
    assert result.engine_used == "graphrag-cli"
    assert captured["timeout_seconds"] == 321


def test_index_strict_fails_when_query_ready_artifacts_are_missing(
    tmp_path, monkeypatch
) -> None:
    service = GraphRAGService(build_settings(tmp_path))

    monkeypatch.setattr(service, "_graphrag_cli_available", lambda: True)
    monkeypatch.setattr(
        service,
        "_run_command",
        lambda command, timeout_seconds=None: type("Result", (), {"returncode": 0})(),
    )
    monkeypatch.setattr(service, "_graphrag_query_artifacts_present", lambda: False)

    result = service.index(IndexRequest(rebuild=True, strict=True))

    assert result.status == "error"
    assert result.engine_used == "graphrag-cli"
    assert "query-ready artifacts" in result.details


def test_graph_data_falls_back_to_document_map_without_graphrag_artifacts(
    tmp_path,
) -> None:
    settings = build_settings(tmp_path)
    corpus_dir = settings.graphrag_input_dir / "wikipedia-medieval-anglo-french-wars"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "brétigny.txt").write_text(
        "Le traité de Brétigny réorganise les possessions anglaises après la guerre.",
        encoding="utf-8",
    )
    (corpus_dir / "calais.txt").write_text(
        "Calais reste un pivot logistique et politique dans le corpus de la guerre.",
        encoding="utf-8",
    )

    service = GraphRAGService(settings)

    data = service.graph_data(query="guerre anglaise", source_prefix="", max_nodes=20)

    assert data.graph_ready is True
    assert data.graph_kind == "document"
    assert data.total_nodes == 2
    assert data.message
    assert data.download_url.endswith("/graph/raw?query=guerre+anglaise&max_nodes=20")


def test_graph_data_reports_missing_corpus_when_no_fallback_documents_exist(tmp_path) -> None:
    service = GraphRAGService(build_settings(tmp_path))

    data = service.graph_data(query="corpus", source_prefix="", max_nodes=20)

    assert data.graph_ready is False
    assert data.graph_kind == "document"
    assert "No local documents" in data.message


def test_query_uses_longer_timeout_for_global_method(tmp_path, monkeypatch) -> None:
    service = GraphRAGService(build_settings(tmp_path))
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_graphrag_cli_available", lambda: True)
    monkeypatch.setattr(service, "_graphrag_query_artifacts_present", lambda: True)
    monkeypatch.setattr(
        service,
        "_rank_documents",
        lambda question, top_k: [
            ScoredDocument(path="input/demo.md", excerpt="demo", score=1)
        ],
    )
    monkeypatch.setattr(
        service,
        "_synthesize_answer",
        lambda question, context, timeout_seconds: ("fallback answer", "local-deterministic"),
    )

    def fake_query(question: str, method: str, response_type: str, timeout_seconds: int):
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        return None

    monkeypatch.setattr(service, "_query_with_graphrag", fake_query)

    result = service.query(
        QueryRequest(question="Compare Bretigny et Troyes.", method="global", top_k=1)
    )

    assert captured["method"] == "global"
    assert captured["timeout_seconds"] == 90
    assert result.engine_used == "local-deterministic"
    assert result.warnings == [
        "GraphRAG CLI global query failed or exceeded its 90s time budget, "
        "so the bridge used deterministic corpus retrieval."
    ]


def test_query_keeps_shorter_timeout_for_local_method(tmp_path, monkeypatch) -> None:
    service = GraphRAGService(build_settings(tmp_path))
    captured: dict[str, object] = {}

    monkeypatch.setattr(service, "_graphrag_cli_available", lambda: True)
    monkeypatch.setattr(service, "_graphrag_query_artifacts_present", lambda: True)
    monkeypatch.setattr(
        service,
        "_rank_documents",
        lambda question, top_k: [
            ScoredDocument(path="input/demo.md", excerpt="demo", score=1)
        ],
    )
    monkeypatch.setattr(
        service,
        "_synthesize_answer",
        lambda question, context, timeout_seconds: ("fallback answer", "local-deterministic"),
    )

    def fake_query(question: str, method: str, response_type: str, timeout_seconds: int):
        captured["method"] = method
        captured["timeout_seconds"] = timeout_seconds
        return None

    monkeypatch.setattr(service, "_query_with_graphrag", fake_query)

    result = service.query(QueryRequest(question="Que fait le bridge ?", top_k=1))

    assert captured["method"] == "local"
    assert captured["timeout_seconds"] == 30
    assert result.engine_used == "local-deterministic"
    assert result.warnings == [
        "GraphRAG CLI local query failed or exceeded its 30s time budget, "
        "so the bridge used deterministic corpus retrieval."
    ]
