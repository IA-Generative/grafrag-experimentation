from __future__ import annotations

import shutil
import socket
from pathlib import Path

from auth import AuthenticatedUser
from config import Settings
from corpus_models import (
    ActionResponse,
    CorpusDetail,
    CorpusManagerConfigResponse,
    CorpusSummary,
    CorpusVersionSummary,
    CreateCorpusRequest,
    JobSummary,
    MeResponse,
    NotificationItem,
)
from corpus_store import CorpusStore
from corpus_store import utcnow
from models import IndexRequest
from service import GraphRAGService
from source_connectors import ConnectorError, build_connector


class CorpusManagerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = CorpusStore(settings)
        self.store.initialize()

    def manager_config(self) -> CorpusManagerConfigResponse:
        return CorpusManagerConfigResponse(
            auth_required=self.settings.corpus_manager_auth_required,
            keycloak_url=self.settings.keycloak_public_url,
            keycloak_js_url=self.settings.keycloak_js_url,
            realm=self.settings.keycloak_realm,
            client_id=self.settings.corpus_manager_client_id,
            openwebui_url=self.settings.openwebui_public_url,
            corpus_manager_url=self.settings.corpus_manager_public_url,
        )

    def me(self, user: AuthenticatedUser) -> MeResponse:
        return MeResponse(
            email=user.email,
            preferred_username=user.preferred_username,
            groups=user.groups,
            roles=user.roles,
            is_admin=user.is_admin,
        )

    def list_corpora(self, user: AuthenticatedUser) -> list[CorpusSummary]:
        return [self._summary_model(item) for item in self.store.list_corpora(user)]

    def get_corpus(self, corpus_id: str, user: AuthenticatedUser) -> CorpusDetail:
        return self._detail_model(self.store.get_corpus(corpus_id, user))

    def create_corpus(self, request: CreateCorpusRequest, user: AuthenticatedUser) -> CorpusDetail:
        return self._detail_model(self.store.create_corpus(request, user))

    def queue_sync(self, corpus_id: str, user: AuthenticatedUser) -> ActionResponse:
        job = self._job_model(self.store.queue_sync_job(corpus_id, user))
        return ActionResponse(status="queued", details="Synchronization queued.", job=job)

    def queue_index(
        self,
        corpus_id: str,
        user: AuthenticatedUser,
        version_id: str | None = None,
    ) -> ActionResponse:
        job = self._job_model(self.store.queue_index_job(corpus_id, user, version_id))
        return ActionResponse(status="queued", details="Indexing queued.", job=job)

    def retry_job(self, job_id: str, user: AuthenticatedUser) -> ActionResponse:
        job = self._job_model(self.store.retry_job(job_id, user))
        return ActionResponse(status="queued", details="Retry queued.", job=job)

    def publish_version(
        self,
        corpus_id: str,
        version_id: str,
        user: AuthenticatedUser,
    ) -> ActionResponse:
        version = self._version_model(
            self.store.publish_version(corpus_id, version_id, user),
            active_version_id=version_id,
        )
        return ActionResponse(status="ok", details="Version published.", version=version)

    def rollback_version(
        self,
        corpus_id: str,
        version_id: str,
        user: AuthenticatedUser,
    ) -> ActionResponse:
        version = self._version_model(
            self.store.publish_version(corpus_id, version_id, user),
            active_version_id=version_id,
        )
        return ActionResponse(status="ok", details="Rollback completed.", version=version)

    def list_jobs(self, corpus_id: str, user: AuthenticatedUser) -> list[JobSummary]:
        return [self._job_model(item) for item in self.store.list_jobs(corpus_id, user)]

    def get_job(self, job_id: str, user: AuthenticatedUser) -> JobSummary:
        return self._job_model(self.store.get_job(job_id, user))

    def get_job_logs(self, job_id: str, user: AuthenticatedUser) -> str:
        return self.store.read_job_log(job_id, user)

    def notifications(self, user: AuthenticatedUser, corpus_id: str | None = None) -> list[NotificationItem]:
        notifications: list[NotificationItem] = []
        for item in self.store.latest_notifications(user):
            if corpus_id and item["corpus_id"] != corpus_id:
                continue
            level = "info"
            if item["status"] == "failed":
                level = "error"
            elif item["status"] == "completed":
                level = "success"
            notifications.append(
                NotificationItem(
                    corpus_id=str(item["corpus_id"]),
                    corpus_name=str(item.get("corpus_name") or item["corpus_id"]),
                    job_id=str(item["id"]),
                    level=level,
                    title=self._notification_title(item),
                    message=self._notification_message(item),
                    created_at=str(item["updated_at"]),
                    link_url=f"{self.settings.corpus_manager_public_url.rstrip('/')}/?corpus={item['corpus_id']}",
                )
            )
        return notifications

    def resolve_query_service(
        self,
        corpus_id: str,
        user: AuthenticatedUser,
    ) -> tuple[GraphRAGService, dict[str, object]]:
        version = self.store.resolve_active_version(corpus_id, user)
        service_settings = self._settings_for_workspace(Path(str(version["workspace_root"])))
        return GraphRAGService(service_settings), version

    def resolve_default_corpus(self, user: AuthenticatedUser) -> str | None:
        published = [
            corpus
            for corpus in self.store.list_corpora(user)
            if corpus.get("active_version_id")
        ]
        if len(published) == 1:
            return str(published[0]["id"])
        return None

    def run_next_job(self, worker_id: str) -> bool:
        job = self.store.claim_next_job(worker_id)
        if job is None:
            return False

        self.store.append_job_log(job["id"], f"Worker {worker_id} claimed {job['job_type']} job.")
        try:
            if job["job_type"] == "sync":
                self._run_sync_job(job)
            elif job["job_type"] == "index":
                self._run_index_job(job)
            else:
                raise RuntimeError(f"Unsupported job type: {job['job_type']}")
        except Exception as error:  # pragma: no cover - defensive path
            self.store.append_job_log(job["id"], f"Unhandled worker error: {error}")
            self.store.mark_job_failed(
                job["id"],
                error_category="worker_error",
                error_summary=str(error),
                error_detail=repr(error),
            )
        return True

    def _run_sync_job(self, job: dict[str, object]) -> None:
        corpus = self.store.get_corpus_record(str(job["corpus_id"]))
        source = corpus["sources"][0] if corpus.get("sources") else None
        if not source:
            self.store.mark_job_failed(
                str(job["id"]),
                error_category="source_missing",
                error_summary="No source is configured for this corpus.",
                error_detail="Configure a source before synchronizing.",
            )
            return

        self.store.mark_job_progress(str(job["id"]), phase="syncing", progress=0.05)
        version = self.store.create_version(str(job["corpus_id"]))
        self._set_job_version(str(job["id"]), str(version["id"]))
        workspace_root = Path(str(version["workspace_root"]))
        snapshot_root = Path(str(version["snapshot_path"]))
        self._prepare_workspace(workspace_root)
        self.store.append_job_log(str(job["id"]), f"Syncing source {source['source_kind']} into {snapshot_root}.")

        try:
            connector = build_connector(str(source["source_kind"]))
            result = connector.fetch(source.get("config", {}))
        except ConnectorError as error:
            self.store.mark_job_failed(
                str(job["id"]),
                error_category="source_unavailable",
                error_summary=str(error),
                error_detail=repr(error),
            )
            self.store.update_version(str(version["id"]), status="failed")
            return

        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        snapshot_root.mkdir(parents=True, exist_ok=True)
        synchronized = 0
        for document in result.documents:
            target_path = (snapshot_root / document.relative_path).resolve()
            if not str(target_path).startswith(str(snapshot_root.resolve())):
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(document.content)
            synchronized += 1

        metrics = {
            "source_kind": source["source_kind"],
            "documents_discovered": result.discovered,
            "documents_synchronized": synchronized,
            "documents_ignored": result.ignored,
            "documents_in_error": result.errors,
            "total_size_bytes": result.total_size_bytes,
            "version_label": version["label"],
        }
        self.store.update_version(
            str(version["id"]),
            status="snapshot_ready",
            document_count=synchronized,
            snapshot_bytes=result.total_size_bytes,
            metrics=metrics,
        )
        self.store.append_job_log(
            str(job["id"]),
            f"Snapshot ready for {version['label']} with {synchronized} synchronized documents.",
        )
        self.store.mark_job_completed(
            str(job["id"]),
            phase="snapshot_ready",
            metrics=metrics,
        )

    def _run_index_job(self, job: dict[str, object]) -> None:
        version_id = str(job.get("version_id") or "")
        if not version_id:
            self.store.mark_job_failed(
                str(job["id"]),
                error_category="version_missing",
                error_summary="No version is associated with this index job.",
                error_detail="Queue indexing from a synchronized corpus version.",
            )
            return

        version = self.store.get_version_record(version_id)
        workspace_root = Path(str(version["workspace_root"]))
        self._prepare_workspace(workspace_root)
        self.store.update_version(version_id, status="indexing")
        self.store.mark_job_progress(str(job["id"]), phase="indexing", progress=0.1)
        self.store.append_job_log(str(job["id"]), f"Indexing workspace {workspace_root}.")

        service = GraphRAGService(self._settings_for_workspace(workspace_root))
        result = service.index(IndexRequest(rebuild=True, strict=False))
        self.store.mark_job_progress(str(job["id"]), phase="validating", progress=0.8)

        metrics = self._collect_index_metrics(workspace_root, service, result.engine_used)
        metrics["details"] = result.details
        metrics["engine_used"] = result.engine_used

        self.store.update_version(
            version_id,
            status="ready",
            metrics={**dict(version.get("metrics", {})), **metrics},
        )
        self.store.append_job_log(str(job["id"]), result.details)
        self.store.mark_job_completed(str(job["id"]), phase="ready", metrics=metrics)

    def _prepare_workspace(self, workspace_root: Path) -> None:
        workspace_root.mkdir(parents=True, exist_ok=True)
        (workspace_root / "input").mkdir(parents=True, exist_ok=True)
        (workspace_root / "output").mkdir(parents=True, exist_ok=True)
        (workspace_root / "cache").mkdir(parents=True, exist_ok=True)
        template_settings = self.settings.graphrag_template_root / "settings.yaml"
        if template_settings.exists():
            shutil.copyfile(template_settings, workspace_root / "settings.yaml")

    def _settings_for_workspace(self, workspace_root: Path) -> Settings:
        payload = self.settings.model_dump()
        payload.update(
            graphrag_root=workspace_root,
            graphrag_input_dir=workspace_root / "input",
            graphrag_output_dir=workspace_root / "output",
            graphrag_cache_dir_override=workspace_root / "cache",
        )
        return Settings(**payload)

    def _collect_index_metrics(
        self,
        workspace_root: Path,
        service: GraphRAGService,
        engine_used: str,
    ) -> dict[str, object]:
        output_root = workspace_root / "output"
        artifacts_bytes = 0
        output_files = 0
        for path in output_root.rglob("*"):
            if not path.is_file():
                continue
            artifacts_bytes += path.stat().st_size
            output_files += 1

        metrics: dict[str, object] = {
            "workspace_root": str(workspace_root),
            "output_files": output_files,
            "artifacts_size_bytes": artifacts_bytes,
            "graph_ready": service.health().graphrag_query_ready,
            "engine_used": engine_used,
        }

        if not metrics["graph_ready"]:
            return metrics

        try:
            import pyarrow.parquet as pq
        except ImportError:
            return metrics

        tables = {
            "entities_count": output_root / "entities.parquet",
            "relationships_count": output_root / "relationships.parquet",
            "communities_count": output_root / "communities.parquet",
        }
        for key, path in tables.items():
            if path.exists():
                metrics[key] = pq.read_table(path).num_rows
        return metrics

    def _set_job_version(self, job_id: str, version_id: str) -> None:
        with self.store.connection() as conn:
            conn.execute(
                "UPDATE jobs SET version_id = ?, updated_at = ? WHERE id = ?",
                (version_id, utcnow(), job_id),
            )

    def _summary_model(self, payload: dict[str, object]) -> CorpusSummary:
        last_job = self._job_model(payload["last_job"]) if payload.get("last_job") else None
        return CorpusSummary(
            id=str(payload["id"]),
            slug=str(payload["slug"]),
            name=str(payload["name"]),
            description=str(payload.get("description") or ""),
            workflow_state=str(payload.get("workflow_state") or "idle"),
            active_version_id=self._optional_str(payload.get("active_version_id")),
            active_version_label=self._optional_str(payload.get("active_version_label")),
            last_job=last_job,
            allowed_groups=[str(item) for item in payload.get("allowed_groups", [])],
            allowed_users=[str(item) for item in payload.get("allowed_users", [])],
            document_count=int(payload.get("document_count") or 0),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
        )

    def _detail_model(self, payload: dict[str, object]) -> CorpusDetail:
        summary = self._summary_model(payload)
        return CorpusDetail(
            **summary.model_dump(),
            sources=[
                {
                    "id": str(item["id"]),
                    "source_kind": str(item["source_kind"]),
                    "source_name": str(item["source_name"]),
                    "config": {str(k): str(v) for k, v in item.get("config", {}).items()},
                }
                for item in payload.get("sources", [])
            ],
            versions=[
                self._version_model(item, active_version_id=summary.active_version_id)
                for item in payload.get("versions", [])
            ],
            jobs=[self._job_model(item) for item in payload.get("jobs", [])],
        )

    def _version_model(
        self,
        payload: dict[str, object],
        *,
        active_version_id: str | None,
    ) -> CorpusVersionSummary:
        return CorpusVersionSummary(
            id=str(payload["id"]),
            label=str(payload["label"]),
            status=str(payload["status"]),
            document_count=int(payload.get("document_count") or 0),
            snapshot_bytes=int(payload.get("snapshot_bytes") or 0),
            created_at=str(payload["created_at"]),
            published_at=self._optional_str(payload.get("published_at")),
            is_active=str(payload["id"]) == str(active_version_id),
            metrics=payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {},
        )

    def _job_model(self, payload: dict[str, object]) -> JobSummary:
        return JobSummary(
            id=str(payload["id"]),
            corpus_id=str(payload["corpus_id"]),
            version_id=self._optional_str(payload.get("version_id")),
            job_type=str(payload["job_type"]),
            status=str(payload["status"]),
            phase=str(payload.get("phase") or payload.get("status") or "queued"),
            progress_percent=float(payload.get("progress_percent") or 0.0),
            requested_by=str(payload.get("requested_by") or ""),
            retry_of_job_id=self._optional_str(payload.get("retry_of_job_id")),
            error_category=self._optional_str(payload.get("error_category")),
            error_summary=self._optional_str(payload.get("error_summary")),
            metrics=payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {},
            created_at=str(payload["created_at"]),
            started_at=self._optional_str(payload.get("started_at")),
            finished_at=self._optional_str(payload.get("finished_at")),
            updated_at=str(payload["updated_at"]),
            logs_url=f"/api/jobs/{payload['id']}/logs",
        )

    def _notification_title(self, payload: dict[str, object]) -> str:
        if payload["status"] == "failed":
            return f"Echec {payload['job_type']}"
        if payload["status"] == "completed":
            return f"{payload['job_type'].capitalize()} terminee"
        if payload["status"] == "running":
            return f"{payload['job_type'].capitalize()} en cours"
        return f"{payload['job_type'].capitalize()} en attente"

    def _notification_message(self, payload: dict[str, object]) -> str:
        progress = float(payload.get("progress_percent") or 0.0)
        if payload["status"] == "failed":
            return str(payload.get("error_summary") or "Le job a echoue.")
        if payload["status"] == "completed":
            return f"{payload['job_type'].capitalize()} terminee pour {payload.get('corpus_name') or payload['corpus_id']}."
        if payload["status"] == "running":
            return (
                f"{payload['job_type'].capitalize()} en cours sur {payload.get('corpus_name') or payload['corpus_id']} "
                f"({progress:.0f}%)."
            )
        return f"{payload['job_type'].capitalize()} en attente pour {payload.get('corpus_name') or payload['corpus_id']}."

    def _optional_str(self, value: object) -> str | None:
        if value in {None, ""}:
            return None
        return str(value)


def default_worker_id() -> str:
    return f"{socket.gethostname()}-worker"
