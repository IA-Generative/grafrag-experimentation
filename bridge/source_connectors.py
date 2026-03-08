from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx


@dataclass
class SourceDocument:
    relative_path: str
    content: bytes
    size_bytes: int


@dataclass
class SyncResult:
    documents: list[SourceDocument]
    discovered: int
    synchronized: int
    ignored: int
    errors: int
    total_size_bytes: int


class ConnectorError(RuntimeError):
    pass


class SourceConnector:
    def fetch(self, config: dict[str, str]) -> SyncResult:
        raise NotImplementedError


class FilesystemConnector(SourceConnector):
    def fetch(self, config: dict[str, str]) -> SyncResult:
        root = Path(config.get("path", "")).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ConnectorError(f"Filesystem source does not exist: {root}")

        documents: list[SourceDocument] = []
        discovered = 0
        ignored = 0
        total_size = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            discovered += 1
            if path.suffix.lower() not in {".md", ".txt"}:
                ignored += 1
                continue
            relative_path = path.relative_to(root).as_posix()
            content = path.read_bytes()
            total_size += len(content)
            documents.append(
                SourceDocument(
                    relative_path=relative_path,
                    content=content,
                    size_bytes=len(content),
                )
            )

        return SyncResult(
            documents=documents,
            discovered=discovered,
            synchronized=len(documents),
            ignored=ignored,
            errors=0,
            total_size_bytes=total_size,
        )


class DriveHttpConnector(SourceConnector):
    def fetch(self, config: dict[str, str]) -> SyncResult:
        base_url = config.get("base_url", "").rstrip("/")
        workspace_id = config.get("workspace_id", "default")
        if not base_url:
            raise ConnectorError("drive-http source requires base_url")

        list_url = urljoin(f"{base_url}/", f"api/workspaces/{workspace_id}/files")
        try:
            with httpx.Client(timeout=30) as client:
                response = client.get(list_url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as error:
            raise ConnectorError(f"Unable to list drive files: {error}") from error

        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            raise ConnectorError("Drive API response is invalid.")

        documents: list[SourceDocument] = []
        discovered = 0
        ignored = 0
        errors = 0
        total_size = 0

        with httpx.Client(timeout=30) as client:
            for item in payload["files"]:
                discovered += 1
                if not isinstance(item, dict):
                    ignored += 1
                    continue
                relative_path = str(item.get("path") or "").strip()
                content_url = str(item.get("content_url") or "").strip()
                if not relative_path or not content_url:
                    ignored += 1
                    continue
                if Path(relative_path).suffix.lower() not in {".md", ".txt"}:
                    ignored += 1
                    continue
                try:
                    content_response = client.get(urljoin(f"{base_url}/", content_url.lstrip("/")))
                    content_response.raise_for_status()
                    content = content_response.content
                except httpx.HTTPError:
                    errors += 1
                    continue
                total_size += len(content)
                documents.append(
                    SourceDocument(
                        relative_path=relative_path,
                        content=content,
                        size_bytes=len(content),
                    )
                )

        return SyncResult(
            documents=documents,
            discovered=discovered,
            synchronized=len(documents),
            ignored=ignored,
            errors=errors,
            total_size_bytes=total_size,
        )


def build_connector(source_kind: str) -> SourceConnector:
    normalized = source_kind.strip().lower()
    if normalized == "filesystem":
        return FilesystemConnector()
    if normalized in {"drive-http", "drive"}:
        return DriveHttpConnector()
    raise ConnectorError(f"Unsupported source kind: {source_kind}")
