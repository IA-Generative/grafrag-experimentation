from __future__ import annotations

import json
import sqlite3
import shutil
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from auth import AuthenticatedUser
from config import Settings
from corpus_models import CreateCorpusRequest


def utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class DuplicateCorpusSlugError(ValueError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"A corpus with slug '{slug}' already exists.")
        self.slug = slug


class CorpusStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.corpus_db_path
        self.root = settings.corpus_manager_root
        self.logs_root = settings.corpus_logs_root
        self.versions_root = settings.corpus_versions_root

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)
        self.versions_root.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            try:
                conn.executescript(
                    """
                    PRAGMA foreign_keys = ON;

                    CREATE TABLE IF NOT EXISTS corpora (
                        id TEXT PRIMARY KEY,
                        slug TEXT NOT NULL UNIQUE,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        workflow_state TEXT NOT NULL DEFAULT 'idle',
                        active_version_id TEXT,
                        created_by TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS corpus_sources (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        source_kind TEXT NOT NULL,
                        source_name TEXT NOT NULL,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS corpus_acl (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        principal_type TEXT NOT NULL,
                        principal_value TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(corpus_id, principal_type, principal_value)
                    );

                    CREATE TABLE IF NOT EXISTS corpus_versions (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        version_number INTEGER NOT NULL,
                        label TEXT NOT NULL,
                        status TEXT NOT NULL,
                        snapshot_path TEXT NOT NULL,
                        workspace_root TEXT NOT NULL,
                        document_count INTEGER NOT NULL DEFAULT 0,
                        snapshot_bytes INTEGER NOT NULL DEFAULT 0,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        published_at TEXT,
                        UNIQUE(corpus_id, version_number)
                    );

                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        version_id TEXT REFERENCES corpus_versions(id) ON DELETE SET NULL,
                        job_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        progress REAL NOT NULL DEFAULT 0,
                        requested_by TEXT NOT NULL DEFAULT '',
                        retry_of_job_id TEXT,
                        error_category TEXT,
                        error_summary TEXT,
                        error_detail TEXT,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        logs_path TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        updated_at TEXT NOT NULL,
                        worker_id TEXT
                    );

                    CREATE INDEX IF NOT EXISTS jobs_status_created_idx
                        ON jobs(status, created_at);
                    CREATE INDEX IF NOT EXISTS jobs_corpus_created_idx
                        ON jobs(corpus_id, created_at DESC);
                    """
                )
            except sqlite3.DatabaseError:
                conn.close()
                timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                backup_path = self.db_path.with_name(
                    f"{self.db_path.stem}.corrupt-{timestamp}{self.db_path.suffix}"
                )
                if self.db_path.exists():
                    self.db_path.replace(backup_path)
                conn = sqlite3.connect(self.db_path)
                conn.executescript(
                    """
                    PRAGMA foreign_keys = ON;
                    CREATE TABLE IF NOT EXISTS corpora (
                        id TEXT PRIMARY KEY,
                        slug TEXT NOT NULL UNIQUE,
                        name TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        workflow_state TEXT NOT NULL DEFAULT 'idle',
                        active_version_id TEXT,
                        created_by TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS corpus_sources (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        source_kind TEXT NOT NULL,
                        source_name TEXT NOT NULL,
                        config_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS corpus_acl (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        principal_type TEXT NOT NULL,
                        principal_value TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(corpus_id, principal_type, principal_value)
                    );
                    CREATE TABLE IF NOT EXISTS corpus_versions (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        version_number INTEGER NOT NULL,
                        label TEXT NOT NULL,
                        status TEXT NOT NULL,
                        snapshot_path TEXT NOT NULL,
                        workspace_root TEXT NOT NULL,
                        document_count INTEGER NOT NULL DEFAULT 0,
                        snapshot_bytes INTEGER NOT NULL DEFAULT 0,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        published_at TEXT,
                        UNIQUE(corpus_id, version_number)
                    );
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        corpus_id TEXT NOT NULL REFERENCES corpora(id) ON DELETE CASCADE,
                        version_id TEXT REFERENCES corpus_versions(id) ON DELETE SET NULL,
                        job_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        progress REAL NOT NULL DEFAULT 0,
                        requested_by TEXT NOT NULL DEFAULT '',
                        retry_of_job_id TEXT,
                        error_category TEXT,
                        error_summary TEXT,
                        error_detail TEXT,
                        metrics_json TEXT NOT NULL DEFAULT '{}',
                        logs_path TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        updated_at TEXT NOT NULL,
                        worker_id TEXT
                    );
                    CREATE INDEX IF NOT EXISTS jobs_status_created_idx
                        ON jobs(status, created_at);
                    CREATE INDEX IF NOT EXISTS jobs_corpus_created_idx
                        ON jobs(corpus_id, created_at DESC);
                    """
                )
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        self.initialize()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def create_corpus(self, request: CreateCorpusRequest, user: AuthenticatedUser) -> dict[str, object]:
        corpus_id = f"corpus-{uuid.uuid4().hex[:12]}"
        source_id = f"source-{uuid.uuid4().hex[:12]}"
        now = utcnow()
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO corpora (
                        id, slug, name, description, workflow_state, active_version_id,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'idle', NULL, ?, ?, ?)
                    """,
                    (
                        corpus_id,
                        request.slug,
                        request.name,
                        request.description,
                        user.email or user.preferred_username,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO corpus_sources (
                        id, corpus_id, source_kind, source_name, config_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_id,
                        corpus_id,
                        request.source_kind,
                        request.source_name,
                        json.dumps(request.source_config, ensure_ascii=True),
                        now,
                        now,
                    ),
                )
                grants = self._normalized_grants(
                    request.allowed_groups,
                    request.allowed_users,
                    user,
                )
                for principal_type, principal_value in grants:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO corpus_acl (
                            corpus_id, principal_type, principal_value, created_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (corpus_id, principal_type, principal_value, now),
                    )
        except sqlite3.IntegrityError as error:
            if "corpora.slug" in str(error):
                raise DuplicateCorpusSlugError(request.slug) from error
            raise
        return self.get_corpus(corpus_id, user)

    def list_corpora(self, user: AuthenticatedUser) -> list[dict[str, object]]:
        with self.connection() as conn:
            corpora = [self._decode_row(row) for row in conn.execute("SELECT * FROM corpora ORDER BY name")]
            return [
                self._hydrate_corpus(conn, corpus["id"])
                for corpus in corpora
                if self._has_access(conn, corpus["id"], user)
            ]

    def get_corpus(self, corpus_id: str, user: AuthenticatedUser) -> dict[str, object]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            return self._hydrate_corpus(conn, corpus_id, include_versions=True, include_jobs=True)

    def get_corpus_record(self, corpus_id: str) -> dict[str, object]:
        with self.connection() as conn:
            return self._hydrate_corpus(conn, corpus_id, include_versions=True, include_jobs=True)

    def delete_corpus(self, corpus_id: str, user: AuthenticatedUser) -> None:
        workspace_roots: list[Path] = []
        log_paths: list[Path] = []
        with self.connection() as conn:
            corpus = self._hydrate_corpus(conn, corpus_id, include_versions=True, include_jobs=True)
            if not self._can_manage(conn, corpus_id, user):
                raise PermissionError("Only the corpus owner or an admin can delete this corpus.")

            active_jobs = [
                item for item in corpus.get("jobs", [])
                if item.get("status") in {"queued", "running"}
            ]
            if active_jobs:
                raise ValueError("Cannot delete a corpus while sync or index jobs are still active.")

            workspace_roots = [
                Path(str(item["workspace_root"]))
                for item in corpus.get("versions", [])
                if item.get("workspace_root")
            ]
            log_paths = [
                Path(str(item["logs_path"]))
                for item in corpus.get("jobs", [])
                if item.get("logs_path")
            ]
            conn.execute("DELETE FROM corpora WHERE id = ?", (corpus_id,))

        for path in workspace_roots:
            shutil.rmtree(path, ignore_errors=True)
        shutil.rmtree(self.versions_root / corpus_id, ignore_errors=True)
        for path in log_paths:
            if path.exists():
                path.unlink(missing_ok=True)
        shutil.rmtree(self.logs_root / corpus_id, ignore_errors=True)

    def queue_sync_job(self, corpus_id: str, user: AuthenticatedUser) -> dict[str, object]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            return self._insert_job(
                conn,
                corpus_id=corpus_id,
                version_id=None,
                job_type="sync",
                requested_by=user.email or user.preferred_username,
                retry_of_job_id=None,
            )

    def queue_index_job(
        self,
        corpus_id: str,
        user: AuthenticatedUser,
        version_id: str | None = None,
    ) -> dict[str, object]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            target_version_id = version_id or self._latest_version_id(conn, corpus_id)
            if not target_version_id:
                raise ValueError("No synchronized corpus version is available yet.")
            version = self._get_version(conn, target_version_id)
            if version is None or version["corpus_id"] != corpus_id:
                raise LookupError(target_version_id)
            return self._insert_job(
                conn,
                corpus_id=corpus_id,
                version_id=target_version_id,
                job_type="index",
                requested_by=user.email or user.preferred_username,
                retry_of_job_id=None,
            )

    def retry_job(self, job_id: str, user: AuthenticatedUser) -> dict[str, object]:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None or not self._has_access(conn, job["corpus_id"], user):
                raise LookupError(job_id)
            if job["status"] not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled jobs can be retried.")
            return self._insert_job(
                conn,
                corpus_id=job["corpus_id"],
                version_id=job["version_id"],
                job_type=job["job_type"],
                requested_by=user.email or user.preferred_username,
                retry_of_job_id=job["id"],
            )

    def publish_version(
        self,
        corpus_id: str,
        version_id: str,
        user: AuthenticatedUser,
    ) -> dict[str, object]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            version = self._get_version(conn, version_id)
            if version is None or version["corpus_id"] != corpus_id:
                raise LookupError(version_id)
            if version["status"] not in {"ready", "published"}:
                raise ValueError("Only ready corpus versions can be published.")

            now = utcnow()
            conn.execute(
                "UPDATE corpus_versions SET status = 'ready', updated_at = ? WHERE corpus_id = ?",
                (now, corpus_id),
            )
            conn.execute(
                """
                UPDATE corpus_versions
                SET status = 'published', published_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, now, version_id),
            )
            conn.execute(
                """
                UPDATE corpora
                SET active_version_id = ?, workflow_state = 'published', updated_at = ?
                WHERE id = ?
                """,
                (version_id, now, corpus_id),
            )
            return self._get_version(conn, version_id) or {}

    def list_jobs(self, corpus_id: str, user: AuthenticatedUser) -> list[dict[str, object]]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            rows = conn.execute(
                "SELECT * FROM jobs WHERE corpus_id = ? ORDER BY created_at DESC",
                (corpus_id,),
            ).fetchall()
            return [self._decode_row(row) for row in rows]

    def get_job(self, job_id: str, user: AuthenticatedUser) -> dict[str, object]:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None or not self._has_access(conn, job["corpus_id"], user):
                raise LookupError(job_id)
            return job

    def get_version_record(self, version_id: str) -> dict[str, object]:
        with self.connection() as conn:
            version = self._get_version(conn, version_id)
            if version is None:
                raise LookupError(version_id)
            return version

    def read_job_log(self, job_id: str, user: AuthenticatedUser) -> str:
        job = self.get_job(job_id, user)
        log_path = Path(str(job["logs_path"]))
        if not log_path.exists():
            return ""
        return log_path.read_text(encoding="utf-8", errors="ignore")

    def resolve_active_version(
        self,
        corpus_id: str,
        user: AuthenticatedUser,
    ) -> dict[str, object]:
        with self.connection() as conn:
            if not self._has_access(conn, corpus_id, user):
                raise LookupError(corpus_id)
            row = conn.execute(
                """
                SELECT v.*
                FROM corpora c
                JOIN corpus_versions v ON v.id = c.active_version_id
                WHERE c.id = ?
                """,
                (corpus_id,),
            ).fetchone()
            if row is None:
                raise ValueError("No published version is available for this corpus.")
            return self._decode_row(row)

    def latest_notifications(self, user: AuthenticatedUser, limit: int = 5) -> list[dict[str, object]]:
        with self.connection() as conn:
            accessible_ids = [
                corpus["id"]
                for corpus in [self._decode_row(row) for row in conn.execute("SELECT * FROM corpora")]
                if self._has_access(conn, corpus["id"], user)
            ]
            if not accessible_ids:
                return []
            placeholders = ",".join("?" * len(accessible_ids))
            rows = conn.execute(
                f"""
                SELECT jobs.*, corpora.name AS corpus_name
                FROM jobs
                JOIN corpora ON corpora.id = jobs.corpus_id
                WHERE jobs.corpus_id IN ({placeholders})
                  AND jobs.status IN ('queued', 'running', 'failed', 'completed')
                ORDER BY jobs.updated_at DESC
                LIMIT ?
                """,
                [*accessible_ids, limit],
            ).fetchall()
            return [self._decode_row(row) for row in rows]

    def claim_next_job(self, worker_id: str) -> dict[str, object] | None:
        self.initialize()
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None

            now = utcnow()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'running', started_at = ?, updated_at = ?, worker_id = ?
                WHERE id = ?
                """,
                (now, now, worker_id, row["id"]),
            )
            conn.execute("COMMIT")
            return self._decode_row(
                conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
            )
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def create_version(self, corpus_id: str) -> dict[str, object]:
        with self.connection() as conn:
            version_number = (
                conn.execute(
                    "SELECT COALESCE(MAX(version_number), 0) + 1 FROM corpus_versions WHERE corpus_id = ?",
                    (corpus_id,),
                ).fetchone()[0]
            )
            version_id = f"version-{uuid.uuid4().hex[:12]}"
            now = utcnow()
            workspace_root = self.versions_root / corpus_id / version_id
            snapshot_path = workspace_root / "input"
            conn.execute(
                """
                INSERT INTO corpus_versions (
                    id, corpus_id, version_number, label, status, snapshot_path,
                    workspace_root, document_count, snapshot_bytes, metrics_json,
                    created_at, updated_at, published_at
                ) VALUES (?, ?, ?, ?, 'syncing', ?, ?, 0, 0, '{}', ?, ?, NULL)
                """,
                (
                    version_id,
                    corpus_id,
                    version_number,
                    f"v{version_number}",
                    str(snapshot_path),
                    str(workspace_root),
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE corpora SET workflow_state = 'syncing', updated_at = ? WHERE id = ?",
                (now, corpus_id),
            )
            return self._get_version(conn, version_id) or {}

    def update_version(
        self,
        version_id: str,
        *,
        status: str,
        document_count: int | None = None,
        snapshot_bytes: int | None = None,
        metrics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self.connection() as conn:
            version = self._get_version(conn, version_id)
            if version is None:
                raise LookupError(version_id)
            updates = {
                "status": status,
                "updated_at": utcnow(),
                "document_count": document_count if document_count is not None else version["document_count"],
                "snapshot_bytes": snapshot_bytes if snapshot_bytes is not None else version["snapshot_bytes"],
                "metrics_json": json.dumps(metrics or version.get("metrics") or {}, ensure_ascii=True),
            }
            conn.execute(
                """
                UPDATE corpus_versions
                SET status = ?, updated_at = ?, document_count = ?, snapshot_bytes = ?, metrics_json = ?
                WHERE id = ?
                """,
                (
                    updates["status"],
                    updates["updated_at"],
                    updates["document_count"],
                    updates["snapshot_bytes"],
                    updates["metrics_json"],
                    version_id,
                ),
            )
            conn.execute(
                "UPDATE corpora SET workflow_state = ?, updated_at = ? WHERE id = ?",
                (status, updates["updated_at"], version["corpus_id"]),
            )
            return self._get_version(conn, version_id) or {}

    def mark_job_progress(
        self,
        job_id: str,
        *,
        phase: str,
        progress: float,
        metrics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None:
                raise LookupError(job_id)
            merged_metrics = dict(job.get("metrics", {}))
            if metrics:
                merged_metrics.update(metrics)
            now = utcnow()
            conn.execute(
                """
                UPDATE jobs
                SET phase = ?, progress = ?, metrics_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    phase,
                    progress,
                    json.dumps(merged_metrics, ensure_ascii=True),
                    now,
                    job_id,
                ),
            )
            conn.execute(
                "UPDATE corpora SET workflow_state = ?, updated_at = ? WHERE id = ?",
                (phase, now, job["corpus_id"]),
            )
            return self._get_job(conn, job_id) or {}

    def mark_job_completed(
        self,
        job_id: str,
        *,
        phase: str,
        metrics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None:
                raise LookupError(job_id)
            merged_metrics = dict(job.get("metrics", {}))
            if metrics:
                merged_metrics.update(metrics)
            now = utcnow()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed', phase = ?, progress = 100, metrics_json = ?,
                    finished_at = ?, updated_at = ?, error_category = NULL,
                    error_summary = NULL, error_detail = NULL
                WHERE id = ?
                """,
                (
                    phase,
                    json.dumps(merged_metrics, ensure_ascii=True),
                    now,
                    now,
                    job_id,
                ),
            )
            conn.execute(
                "UPDATE corpora SET workflow_state = ?, updated_at = ? WHERE id = ?",
                (phase, now, job["corpus_id"]),
            )
            return self._get_job(conn, job_id) or {}

    def mark_job_failed(
        self,
        job_id: str,
        *,
        error_category: str,
        error_summary: str,
        error_detail: str,
        phase: str = "failed",
        metrics: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None:
                raise LookupError(job_id)
            merged_metrics = dict(job.get("metrics", {}))
            if metrics:
                merged_metrics.update(metrics)
            now = utcnow()
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', phase = ?, metrics_json = ?, finished_at = ?, updated_at = ?,
                    error_category = ?, error_summary = ?, error_detail = ?
                WHERE id = ?
                """,
                (
                    phase,
                    json.dumps(merged_metrics, ensure_ascii=True),
                    now,
                    now,
                    error_category,
                    error_summary,
                    error_detail,
                    job_id,
                ),
            )
            conn.execute(
                "UPDATE corpora SET workflow_state = 'failed', updated_at = ? WHERE id = ?",
                (now, job["corpus_id"]),
            )
            return self._get_job(conn, job_id) or {}

    def append_job_log(self, job_id: str, message: str) -> None:
        with self.connection() as conn:
            job = self._get_job(conn, job_id)
            if job is None:
                raise LookupError(job_id)
            log_path = Path(str(job["logs_path"]))
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"[{utcnow()}] {message}\n")

    def _insert_job(
        self,
        conn: sqlite3.Connection,
        *,
        corpus_id: str,
        version_id: str | None,
        job_type: str,
        requested_by: str,
        retry_of_job_id: str | None,
    ) -> dict[str, object]:
        now = utcnow()
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        logs_path = str(self.logs_root / corpus_id / f"{job_id}.log")
        conn.execute(
            """
            INSERT INTO jobs (
                id, corpus_id, version_id, job_type, status, phase, progress,
                requested_by, retry_of_job_id, error_category, error_summary,
                error_detail, metrics_json, logs_path, created_at, started_at,
                finished_at, updated_at, worker_id
            ) VALUES (?, ?, ?, ?, 'queued', 'queued', 0, ?, ?, NULL, NULL, NULL, '{}', ?, ?, NULL, NULL, ?, NULL)
            """,
            (
                job_id,
                corpus_id,
                version_id,
                job_type,
                requested_by,
                retry_of_job_id,
                logs_path,
                now,
                now,
            ),
        )
        conn.execute(
            "UPDATE corpora SET workflow_state = 'queued', updated_at = ? WHERE id = ?",
            (now, corpus_id),
        )
        return self._get_job(conn, job_id) or {}

    def _hydrate_corpus(
        self,
        conn: sqlite3.Connection,
        corpus_id: str,
        *,
        include_versions: bool = False,
        include_jobs: bool = False,
    ) -> dict[str, object]:
        corpus_row = conn.execute("SELECT * FROM corpora WHERE id = ?", (corpus_id,)).fetchone()
        if corpus_row is None:
            raise LookupError(corpus_id)
        corpus = self._decode_row(corpus_row)
        source_rows = conn.execute(
            "SELECT * FROM corpus_sources WHERE corpus_id = ? ORDER BY created_at",
            (corpus_id,),
        ).fetchall()
        acl_rows = conn.execute(
            "SELECT principal_type, principal_value FROM corpus_acl WHERE corpus_id = ? ORDER BY principal_type, principal_value",
            (corpus_id,),
        ).fetchall()
        version_rows = conn.execute(
            "SELECT * FROM corpus_versions WHERE corpus_id = ? ORDER BY version_number DESC",
            (corpus_id,),
        ).fetchall()
        job_rows = conn.execute(
            "SELECT * FROM jobs WHERE corpus_id = ? ORDER BY created_at DESC LIMIT 20",
            (corpus_id,),
        ).fetchall()

        versions = [self._decode_row(row) for row in version_rows]
        jobs = [self._decode_row(row) for row in job_rows]
        active_version = next(
            (item for item in versions if item["id"] == corpus.get("active_version_id")),
            None,
        )
        corpus["sources"] = [self._decode_row(row) for row in source_rows]
        corpus["allowed_groups"] = [
            row["principal_value"] for row in acl_rows if row["principal_type"] == "group"
        ]
        corpus["allowed_users"] = [
            row["principal_value"] for row in acl_rows if row["principal_type"] == "user"
        ]
        corpus["active_version_label"] = active_version["label"] if active_version else None
        corpus["document_count"] = int(active_version["document_count"]) if active_version else 0
        corpus["last_job"] = jobs[0] if jobs else None
        if include_versions:
            corpus["versions"] = versions
        if include_jobs:
            corpus["jobs"] = jobs
        return corpus

    def _has_access(
        self,
        conn: sqlite3.Connection,
        corpus_id: str,
        user: AuthenticatedUser,
    ) -> bool:
        if user.is_admin:
            return True
        row = conn.execute(
            "SELECT created_by FROM corpora WHERE id = ?",
            (corpus_id,),
        ).fetchone()
        if row is None:
            return False
        if user.email and row["created_by"] == user.email:
            return True
        grants = conn.execute(
            "SELECT principal_type, principal_value FROM corpus_acl WHERE corpus_id = ?",
            (corpus_id,),
        ).fetchall()
        if not grants:
            return False
        user_groups = set(user.groups)
        for grant in grants:
            if grant["principal_type"] == "user" and user.email and grant["principal_value"] == user.email:
                return True
            if grant["principal_type"] == "group" and grant["principal_value"] in user_groups:
                return True
        return False

    def _can_manage(
        self,
        conn: sqlite3.Connection,
        corpus_id: str,
        user: AuthenticatedUser,
    ) -> bool:
        if user.is_admin:
            return True
        row = conn.execute(
            "SELECT created_by FROM corpora WHERE id = ?",
            (corpus_id,),
        ).fetchone()
        if row is None:
            raise LookupError(corpus_id)
        return bool(user.email and row["created_by"] == user.email)

    def _latest_version_id(self, conn: sqlite3.Connection, corpus_id: str) -> str | None:
        row = conn.execute(
            "SELECT id FROM corpus_versions WHERE corpus_id = ? ORDER BY version_number DESC LIMIT 1",
            (corpus_id,),
        ).fetchone()
        return str(row["id"]) if row else None

    def _get_version(self, conn: sqlite3.Connection, version_id: str) -> dict[str, object] | None:
        row = conn.execute("SELECT * FROM corpus_versions WHERE id = ?", (version_id,)).fetchone()
        return self._decode_row(row) if row else None

    def _get_job(self, conn: sqlite3.Connection, job_id: str) -> dict[str, object] | None:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._decode_row(row) if row else None

    def _normalized_grants(
        self,
        groups: list[str],
        users: list[str],
        actor: AuthenticatedUser,
    ) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        for value in groups:
            cleaned = value.strip()
            if cleaned:
                normalized.append(("group", cleaned))
        for value in users:
            cleaned = value.strip()
            if cleaned:
                normalized.append(("user", cleaned))
        if actor.email:
            normalized.append(("user", actor.email))
        return sorted(set(normalized))

    def _decode_row(self, row: sqlite3.Row | None) -> dict[str, object]:
        if row is None:
            return {}
        payload = {key: row[key] for key in row.keys()}
        for key in ("config_json", "metrics_json"):
            if key in payload:
                raw_value = payload.pop(key)
                try:
                    payload[key.replace("_json", "")] = (
                        json.loads(raw_value) if raw_value else {}
                    )
                except json.JSONDecodeError:
                    payload[key.replace("_json", "")] = {}
        if "progress" in payload:
            payload["progress_percent"] = float(payload.pop("progress") or 0) * 100.0
        return payload
