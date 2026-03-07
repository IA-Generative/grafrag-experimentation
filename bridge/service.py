import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import httpx

from config import Settings
from models import (
    Citation,
    GraphDataResponse,
    GraphEdge,
    GraphNode,
    GraphSourceOption,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    QueryRequest,
    QueryResponse,
)

LOGGER = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_/-]{3,}")


@dataclass
class ScoredDocument:
    path: str
    excerpt: str
    score: int


class GraphRAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health(self) -> HealthResponse:
        self._ensure_layout()
        return HealthResponse(
            status="ok",
            graphrag_cli_available=self._graphrag_cli_available(),
            index_present=self._index_present(),
            graphrag_query_ready=self._graphrag_query_artifacts_present(),
            llm_configured=self.settings.llm_ready,
        )

    def config_snapshot(self) -> dict[str, object]:
        return {
            "openai_api_base": self.settings.openai_api_base,
            "openai_model": self.settings.openai_model,
            "openai_embedding_model": self.settings.openai_embedding_model,
            "openai_api_key_configured": self.settings.llm_ready,
            "bridge_public_url": self.settings.bridge_public_url,
            "graph_viewer_auth_required": self.settings.graph_viewer_auth_required,
            "keycloak_public_url": self.settings.keycloak_public_url,
            "graph_viewer_client_id": self.settings.graph_viewer_client_id,
            "graphrag_root": str(self.settings.graphrag_root),
            "graphrag_input_dir": str(self.settings.graphrag_input_dir),
            "graphrag_output_dir": str(self.settings.graphrag_output_dir),
            "graphrag_cache_dir": str(self.settings.graphrag_cache_dir),
            "graphrag_cache_s3_enabled": self.settings.graphrag_cache_s3_enabled,
            "graphrag_cache_s3_bucket": self.settings.graphrag_cache_s3_bucket,
            "graphrag_cache_s3_prefix": self.settings.graphrag_cache_s3_prefix,
            "graphrag_method": self.settings.graphrag_method,
            "graphrag_top_k": self.settings.graphrag_top_k,
            "graphrag_query_ready": self._graphrag_query_artifacts_present(),
        }

    def query(self, request: QueryRequest) -> QueryResponse:
        self._ensure_layout()
        method = request.method or self.settings.graphrag_method
        response_type = request.response_type or self.settings.graphrag_response_type
        top_k = request.top_k or self.settings.graphrag_top_k
        warnings: list[str] = []
        graph_url = self._build_graph_url(request.question)
        deadline = time.monotonic() + max(5, self.settings.request_timeout_seconds)

        if self._graphrag_cli_available() and self._graphrag_query_artifacts_present():
            cli_timeout = min(
                self.settings.graphrag_cli_timeout_seconds,
                self._remaining_seconds(deadline, reserve_seconds=10),
            )
            cli_output = self._query_with_graphrag(
                request.question,
                method,
                response_type,
                cli_timeout,
            )
            if cli_output:
                ranked_documents = self._rank_documents(request.question, top_k)
                citations = [
                    Citation(path=document.path, excerpt=document.excerpt)
                    for document in ranked_documents
                ] or self._citations_from_manifest(limit=top_k)
                graph_url = self._build_graph_url(
                    request.question,
                    self._dominant_source_filter([document.path for document in ranked_documents]),
                )
                return QueryResponse(
                    answer=cli_output,
                    citations=citations,
                    method=method,
                    engine_used="graphrag-cli",
                    warnings=warnings,
                    raw_output=cli_output,
                    graph_url=graph_url,
                )
            if cli_timeout <= 0:
                warnings.append(
                    "GraphRAG CLI skipped because the remaining request budget was too low."
                )
            else:
                warnings.append(
                    "GraphRAG CLI query failed or exceeded its time budget, so the bridge used deterministic corpus retrieval."
                )
        else:
            warnings.append(
                "GraphRAG CLI or query-ready index artifacts are unavailable, so the bridge used deterministic corpus retrieval."
            )

        ranked_documents = self._rank_documents(request.question, top_k)
        citations = [
            Citation(path=document.path, excerpt=document.excerpt)
            for document in ranked_documents
        ]
        graph_url = self._build_graph_url(
            request.question,
            self._dominant_source_filter([document.path for document in ranked_documents]),
        )
        if not ranked_documents:
            answer = (
                "No local documents were found in the GraphRAG corpus. "
                "Add files under graphrag/input and run the indexing workflow first."
            )
            warnings.append("The corpus directory is empty.")
            return QueryResponse(
                answer=answer,
                citations=[],
                method=method,
                engine_used="local-deterministic",
                warnings=warnings,
                graph_url=graph_url,
            )

        context = self._build_context(ranked_documents, response_type)
        llm_timeout = min(
            self.settings.llm_timeout_seconds,
            self._remaining_seconds(deadline, reserve_seconds=2),
        )
        answer, engine_used = self._synthesize_answer(
            request.question,
            context,
            llm_timeout,
        )
        if engine_used == "local-deterministic" and self.settings.llm_ready and llm_timeout <= 0:
            warnings.append(
                "LLM synthesis skipped because the remaining request budget was too low."
            )
        return QueryResponse(
            answer=answer,
            citations=citations,
            method=method,
            engine_used=engine_used,
            warnings=warnings,
            graph_url=graph_url,
        )

    def graph_data(
        self,
        query: str = "",
        source_prefix: str = "",
        max_nodes: int = 80,
        min_weight: float = 1.0,
    ) -> GraphDataResponse:
        self._ensure_layout()
        normalized_query = query.strip()
        normalized_source = source_prefix.strip()
        available_sources = self._available_source_options()
        download_url = self._graph_download_url()

        if not self._graphrag_query_artifacts_present():
            return GraphDataResponse(
                graph_ready=False,
                query=normalized_query,
                source_prefix=normalized_source,
                max_nodes=max_nodes,
                min_weight=min_weight,
                available_sources=available_sources,
                message=(
                    "Graph artifacts are not ready yet. Run ./scripts/index_corpus.sh first "
                    "and wait until community reports plus LanceDB tables are generated."
                ),
                download_url=download_url,
            )

        try:
            import pyarrow.parquet as pq
        except ImportError:
            return GraphDataResponse(
                graph_ready=False,
                query=normalized_query,
                source_prefix=normalized_source,
                max_nodes=max_nodes,
                min_weight=min_weight,
                available_sources=available_sources,
                message="pyarrow n'est pas disponible dans l'environnement du bridge.",
                download_url=download_url,
            )

        entities_path = self.settings.graphrag_output_dir / "entities.parquet"
        relationships_path = self.settings.graphrag_output_dir / "relationships.parquet"
        documents_path = self.settings.graphrag_output_dir / "documents.parquet"

        try:
            entities = pq.read_table(entities_path).to_pylist()
            relationships = pq.read_table(relationships_path).to_pylist()
            documents = pq.read_table(documents_path).to_pylist()
        except Exception as error:  # pragma: no cover - defensive path for corrupt artifacts
            LOGGER.warning("Unable to load graph artifacts: %s", error)
            return GraphDataResponse(
                graph_ready=False,
                query=normalized_query,
                source_prefix=normalized_source,
                max_nodes=max_nodes,
                min_weight=min_weight,
                available_sources=available_sources,
                message=f"Graph artifacts could not be loaded: {error}",
                download_url=download_url,
            )

        text_unit_to_documents = self._build_text_unit_document_index(documents)
        entity_index = self._build_entity_index(entities, text_unit_to_documents)
        query_tokens = set(self._tokenize(normalized_query))

        candidate_edges: list[tuple[float, GraphEdge]] = []
        for relationship in relationships:
            source = str(relationship.get("source") or "").strip()
            target = str(relationship.get("target") or "").strip()
            if not source or not target:
                continue

            weight = float(relationship.get("weight") or 0.0)
            if weight < min_weight:
                continue

            relationship_documents = sorted(
                self._document_paths_for_text_units(
                    relationship.get("text_unit_ids"), text_unit_to_documents
                )
            )
            if not relationship_documents:
                relationship_documents = sorted(
                    set(entity_index.get(source, {}).get("document_paths", []))
                    | set(entity_index.get(target, {}).get("document_paths", []))
                )

            if normalized_source and not any(
                self._source_matches(path, normalized_source)
                for path in relationship_documents
            ):
                continue

            description = str(relationship.get("description") or "").strip()
            edge_match = self._graph_match_score(
                query_tokens, [source, target, description, *relationship_documents]
            )
            node_match = self._entity_relevance(entity_index.get(source), query_tokens) + (
                self._entity_relevance(entity_index.get(target), query_tokens)
            )

            if query_tokens and edge_match == 0 and node_match == 0:
                continue

            candidate_edges.append(
                (
                    weight + (edge_match * 6) + (node_match * 2),
                    GraphEdge(
                        source=source,
                        target=target,
                        description=description,
                        weight=weight,
                        document_paths=relationship_documents,
                    ),
                )
            )

        if not candidate_edges:
            if query_tokens:
                message = "Aucun sous-graphe ne correspond à la question demandée."
            elif normalized_source:
                message = f"Aucun lien du graphe ne correspond au filtre de source '{normalized_source}'."
            else:
                message = "Le graphe est disponible, mais aucun lien ne correspond aux filtres actuels."
            return GraphDataResponse(
                graph_ready=True,
                query=normalized_query,
                source_prefix=normalized_source,
                max_nodes=max_nodes,
                min_weight=min_weight,
                available_sources=available_sources,
                message=message,
                download_url=download_url,
            )

        candidate_edges.sort(key=lambda item: item[0], reverse=True)

        selected_edges: list[GraphEdge] = []
        selected_nodes: set[str] = set()
        for _, edge in candidate_edges:
            proposed_nodes = selected_nodes | {edge.source, edge.target}
            if selected_edges and len(proposed_nodes) > max_nodes and not {
                edge.source,
                edge.target,
            }.issubset(selected_nodes):
                continue
            selected_edges.append(edge)
            selected_nodes = proposed_nodes
            if len(selected_nodes) >= max_nodes and len(selected_edges) >= max(8, max_nodes // 3):
                break

        if not selected_edges:
            selected_edges = [candidate_edges[0][1]]
            selected_nodes = {selected_edges[0].source, selected_edges[0].target}

        nodes: list[GraphNode] = []
        for node_id in sorted(
            selected_nodes,
            key=lambda item: (
                self._entity_relevance(entity_index.get(item), query_tokens),
                int(entity_index.get(item, {}).get("degree", 0)),
            ),
            reverse=True,
        ):
            entity = entity_index.get(node_id, {})
            nodes.append(
                GraphNode(
                    id=node_id,
                    label=node_id,
                    entity_type=str(entity.get("entity_type") or ""),
                    description=str(entity.get("description") or ""),
                    degree=int(entity.get("degree") or 0),
                    frequency=int(entity.get("frequency") or 0),
                    size=float(max(8, min(32, 8 + int(entity.get("degree") or 0)))),
                    source_group=self._dominant_source_group(
                        entity.get("document_paths", [])
                    ),
                    document_paths=list(entity.get("document_paths", [])),
                )
            )

        message = ""
        if normalized_query:
            message = "Vue ciblée autour des termes de la question."
        elif normalized_source:
            message = f"Vue filtrée sur les éléments du graphe issus de '{normalized_source}'."
        else:
            message = "Liens les plus saillants dans le corpus actuellement indexé."

        return GraphDataResponse(
            graph_ready=True,
            query=normalized_query,
            source_prefix=normalized_source,
            max_nodes=max_nodes,
            min_weight=min_weight,
            total_nodes=len(nodes),
            total_edges=len(selected_edges),
            available_sources=available_sources,
            nodes=nodes,
            edges=selected_edges,
            message=message,
            download_url=download_url,
        )

    def index(self, request: IndexRequest) -> IndexResponse:
        self._ensure_layout()
        manifest_path = self.settings.graphrag_output_dir / "index-manifest.json"

        if self._graphrag_cli_available():
            cli_result = self._run_command(
                [
                    "graphrag",
                    "index",
                    "--root",
                    str(self.settings.graphrag_root),
                ]
            )
            if cli_result and cli_result.returncode == 0:
                details = "GraphRAG CLI indexing completed successfully."
                if manifest_path.exists():
                    details = (
                        f"{details} Existing manifest retained at {manifest_path}."
                    )
                return IndexResponse(
                    status="ok",
                    engine_used="graphrag-cli",
                    details=details,
                )

        manifest = self._write_manifest(rebuild=request.rebuild)
        return IndexResponse(
            status="ok",
            engine_used="fallback-manifest",
            details=f"Generated a lightweight manifest at {manifest}.",
        )

    def _ensure_layout(self) -> None:
        self.settings.graphrag_root.mkdir(parents=True, exist_ok=True)
        self.settings.graphrag_input_dir.mkdir(parents=True, exist_ok=True)
        self.settings.graphrag_output_dir.mkdir(parents=True, exist_ok=True)
        self.settings.graphrag_cache_dir.mkdir(parents=True, exist_ok=True)

    def _graphrag_cli_available(self) -> bool:
        return shutil.which("graphrag") is not None

    def _index_present(self) -> bool:
        manifest_path = self.settings.graphrag_output_dir / "index-manifest.json"
        if manifest_path.exists():
            return True
        for candidate in self.settings.graphrag_output_dir.rglob("*"):
            if candidate.is_file() and candidate.name not in {".gitkeep", "README.md"}:
                return True
        return False

    def _graphrag_query_artifacts_present(self) -> bool:
        required_files = [
            self.settings.graphrag_output_dir / "entities.parquet",
            self.settings.graphrag_output_dir / "relationships.parquet",
            self.settings.graphrag_output_dir / "communities.parquet",
            self.settings.graphrag_output_dir / "community_reports.parquet",
            self.settings.graphrag_output_dir / "graph.graphml",
        ]
        if not all(path.exists() for path in required_files):
            return False

        lancedb_root = self.settings.graphrag_output_dir / "lancedb"
        if not lancedb_root.is_dir():
            return False

        return any(
            candidate.is_dir() and candidate.name.endswith(".lance")
            for candidate in lancedb_root.iterdir()
        )

    def _query_with_graphrag(
        self,
        question: str,
        method: str,
        response_type: str,
        timeout_seconds: int,
    ) -> str | None:
        if timeout_seconds <= 0:
            return None
        result = self._run_command(
            [
                "graphrag",
                "query",
                "--root",
                str(self.settings.graphrag_root),
                "--data",
                str(self.settings.graphrag_output_dir),
                "--method",
                method,
                "--response-type",
                response_type,
                question,
            ],
            timeout_seconds=timeout_seconds,
        )
        if not result or result.returncode != 0:
            return None
        return result.stdout.strip() or result.stderr.strip() or None

    def _run_command(
        self,
        command: list[str],
        timeout_seconds: int | None = None,
    ) -> subprocess.CompletedProcess[str] | None:
        env = os.environ.copy()
        env["SCW_LLM_BASE_URL"] = self.settings.openai_api_base
        env["SCW_SECRET_KEY_LLM"] = self.settings.openai_api_key
        env["SCW_LLM_MODEL"] = self.settings.openai_model
        env["OPENAI_API_BASE"] = self.settings.openai_api_base
        env["OPENAI_API_KEY"] = self.settings.openai_api_key
        env["OPENAI_MODEL"] = self.settings.openai_model

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds or self.settings.request_timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired as error:
            LOGGER.warning(
                "Command timed out after %ss: %s",
                error.timeout,
                " ".join(command),
            )
            return None
        except (OSError, subprocess.SubprocessError) as error:
            LOGGER.warning("Command failed to start: %s", error)
            return None

        if result.returncode != 0:
            LOGGER.warning(
                "Command failed with exit code %s: %s",
                result.returncode,
                result.stderr.strip(),
            )
        return result

    def _write_manifest(self, rebuild: bool) -> Path:
        manifest_path = self.settings.graphrag_output_dir / "index-manifest.json"
        if manifest_path.exists() and not rebuild:
            return manifest_path

        payload = {
            "documents": [],
            "generated_by": "fallback-manifest",
        }
        for path in sorted(self.settings.graphrag_input_dir.rglob("*")):
            if path.is_file():
                payload["documents"].append(
                    {
                        "path": str(path.relative_to(self.settings.graphrag_root)),
                        "size_bytes": path.stat().st_size,
                    }
                )
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return manifest_path

    def _rank_documents(self, question: str, top_k: int) -> list[ScoredDocument]:
        question_tokens = set(self._tokenize(question))
        ranked: list[ScoredDocument] = []
        for path in sorted(self.settings.graphrag_input_dir.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            excerpt = self._excerpt(text)
            if not excerpt:
                continue
            document_tokens = self._tokenize(text)
            overlap = sum(1 for token in document_tokens if token in question_tokens)
            if overlap == 0:
                overlap = 1
            ranked.append(
                ScoredDocument(
                    path=str(path.relative_to(self.settings.graphrag_root)),
                    excerpt=excerpt,
                    score=overlap,
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _tokenize(self, value: str) -> list[str]:
        return [token.lower() for token in TOKEN_PATTERN.findall(value)]

    def _excerpt(self, value: str, limit: int = 280) -> str:
        compact = " ".join(value.split())
        return compact[:limit]

    def _build_context(self, ranked_documents: list[ScoredDocument], response_type: str) -> str:
        lines = [f"Requested response type: {response_type}", ""]
        for document in ranked_documents:
            lines.append(f"Source: {document.path}")
            lines.append(f"Excerpt: {document.excerpt}")
            lines.append("")
        return "\n".join(lines).strip()

    def _synthesize_answer(
        self,
        question: str,
        context: str,
        llm_timeout_seconds: int,
    ) -> tuple[str, str]:
        if self.settings.llm_ready and llm_timeout_seconds > 0:
            answer = self._synthesize_with_llm(question, context, llm_timeout_seconds)
            if answer:
                return answer, "external-openai-compatible"
        return self._fallback_answer(question, context), "local-deterministic"

    def _synthesize_with_llm(
        self,
        question: str,
        context: str,
        timeout_seconds: int,
    ) -> str | None:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.openai_model,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer strictly from the provided GraphRAG context. "
                        "If evidence is thin, say so explicitly."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question:\n{question}\n\nContext:\n{context}",
                },
            ],
        }
        try:
            with httpx.Client(timeout=timeout_seconds) as client:
                response = client.post(
                    self.settings.chat_completions_url,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as error:
            LOGGER.warning("LLM synthesis failed: %s", error)
            return None

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return None
        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "\n".join(part for part in text_parts if part).strip() or None
        return None

    def _fallback_answer(self, question: str, context: str) -> str:
        return (
            "GraphRAG fallback answer\n\n"
            f"Question: {question}\n\n"
            "The bridge did not use a live LLM response, so the answer is based on the "
            "highest-ranked local corpus excerpts below.\n\n"
            f"{context}"
        )

    def _remaining_seconds(self, deadline: float, reserve_seconds: int = 0) -> int:
        return max(0, int(deadline - time.monotonic() - reserve_seconds))

    def _citations_from_manifest(self, limit: int) -> list[Citation]:
        manifest_path = self.settings.graphrag_output_dir / "index-manifest.json"
        citations: list[Citation] = []
        if manifest_path.exists():
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for item in data.get("documents", [])[:limit]:
                citations.append(Citation(path=item.get("path", "unknown"), excerpt=""))
        if citations:
            return citations

        for path in sorted(self.settings.graphrag_input_dir.rglob("*")):
            if not path.is_file():
                continue
            citations.append(
                Citation(
                    path=str(path.relative_to(self.settings.graphrag_root)),
                    excerpt="",
                )
            )
            if len(citations) >= limit:
                break
        return citations

    def _build_graph_url(self, question: str = "", source_prefix: str = "") -> str:
        params: dict[str, str] = {}
        if question.strip():
            params["query"] = question.strip()
        if source_prefix.strip():
            params["source_prefix"] = source_prefix.strip()
        suffix = f"?{urlencode(params)}" if params else ""
        return f"{self.settings.bridge_public_url.rstrip('/')}/graph{suffix}"

    def _graph_download_url(self) -> str:
        return f"{self.settings.bridge_public_url.rstrip('/')}/graph/raw"

    def _available_source_options(self) -> list[GraphSourceOption]:
        options = [GraphSourceOption(id="", label="All documents")]
        prefixes: set[str] = set()
        has_root_files = False

        for path in sorted(self.settings.graphrag_input_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(self.settings.graphrag_input_dir)
            if len(relative_path.parts) == 1:
                has_root_files = True
            else:
                prefixes.add(relative_path.parts[0])

        if has_root_files:
            options.append(GraphSourceOption(id="__root__", label="Root-level documents"))
        for prefix in sorted(prefixes):
            options.append(GraphSourceOption(id=prefix, label=prefix))
        return options

    def _build_text_unit_document_index(
        self, documents: list[dict[str, object]]
    ) -> dict[str, set[str]]:
        available_input_paths = self._scan_input_document_paths()
        index: dict[str, set[str]] = {}

        for document in documents:
            title = str(document.get("title") or "").strip()
            resolved_path = self._resolve_document_path(title, available_input_paths)
            if not resolved_path:
                continue

            for text_unit_id in document.get("text_unit_ids") or []:
                index.setdefault(str(text_unit_id), set()).add(resolved_path)

        return index

    def _scan_input_document_paths(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for path in sorted(self.settings.graphrag_input_dir.rglob("*")):
            if not path.is_file():
                continue
            relative_path = str(path.relative_to(self.settings.graphrag_root))
            index.setdefault(path.name, []).append(relative_path)
        return index

    def _resolve_document_path(
        self, title: str, available_input_paths: dict[str, list[str]]
    ) -> str:
        if not title:
            return ""
        normalized = title.replace("\\", "/").lstrip("./")
        if normalized.startswith("input/"):
            return normalized
        candidates = available_input_paths.get(Path(normalized).name, [])
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            candidates = sorted(
                candidates,
                key=lambda path: (
                    "wikipedia-medieval-anglo-french-wars" not in path,
                    len(path),
                    path,
                ),
            )
            return candidates[0]
        return ""

    def _build_entity_index(
        self,
        entities: list[dict[str, object]],
        text_unit_to_documents: dict[str, set[str]],
    ) -> dict[str, dict[str, object]]:
        entity_index: dict[str, dict[str, object]] = {}
        for entity in entities:
            title = str(entity.get("title") or entity.get("id") or "").strip()
            if not title:
                continue
            document_paths = sorted(
                self._document_paths_for_text_units(
                    entity.get("text_unit_ids"), text_unit_to_documents
                )
            )
            entity_index[title] = {
                "entity_type": str(entity.get("type") or ""),
                "description": str(entity.get("description") or ""),
                "degree": int(entity.get("degree") or 0),
                "frequency": int(entity.get("frequency") or 0),
                "document_paths": document_paths,
            }
        return entity_index

    def _document_paths_for_text_units(
        self,
        text_unit_ids: object,
        text_unit_to_documents: dict[str, set[str]],
    ) -> set[str]:
        document_paths: set[str] = set()
        for text_unit_id in text_unit_ids or []:
            document_paths |= text_unit_to_documents.get(str(text_unit_id), set())
        return document_paths

    def _graph_match_score(self, query_tokens: set[str], values: list[str]) -> int:
        if not query_tokens:
            return 0
        haystack = set(self._tokenize(" ".join(value for value in values if value)))
        return len(query_tokens & haystack)

    def _entity_relevance(
        self, entity: dict[str, object] | None, query_tokens: set[str]
    ) -> int:
        if not entity or not query_tokens:
            return 0
        return self._graph_match_score(
            query_tokens,
            [
                str(entity.get("description") or ""),
                str(entity.get("entity_type") or ""),
                *list(entity.get("document_paths", [])),
            ],
        )

    def _dominant_source_group(self, document_paths: list[str]) -> str:
        if not document_paths:
            return "unknown"
        counts: dict[str, int] = {}
        for path in document_paths:
            group = self._source_group_for_path(path)
            counts[group] = counts.get(group, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]

    def _source_group_for_path(self, path: str) -> str:
        normalized = path.replace("\\", "/")
        if not normalized.startswith("input/"):
            return "unknown"
        remainder = normalized[len("input/") :]
        if "/" not in remainder:
            return "__root__"
        return remainder.split("/", 1)[0]

    def _source_matches(self, path: str, source_prefix: str) -> bool:
        if not source_prefix:
            return True
        group = self._source_group_for_path(path)
        return group == source_prefix

    def _dominant_source_filter(self, paths: list[str]) -> str:
        counts: dict[str, int] = {}
        for path in paths:
            group = self._source_group_for_path(path)
            if group == "unknown":
                continue
            counts[group] = counts.get(group, 0) + 1
        if not counts:
            return ""
        return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
