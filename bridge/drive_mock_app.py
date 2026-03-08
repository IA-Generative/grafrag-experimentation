from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


DRIVE_ROOT = Path("/app/drive-data")
app = FastAPI(title="Drive Mock", version="0.1.0")


class CreateDriveFileRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str = Field(min_length=1)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "drive-mock", "status": "ok"}


@app.get("/api/workspaces/{workspace_id}/files")
def list_files(workspace_id: str) -> dict[str, object]:
    workspace_root = DRIVE_ROOT / workspace_id
    files: list[dict[str, object]] = []
    if workspace_root.exists():
        for path in sorted(workspace_root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(workspace_root).as_posix()
            files.append(
                {
                    "path": relative_path,
                    "size_bytes": path.stat().st_size,
                    "content_url": f"/api/workspaces/{workspace_id}/raw/{relative_path}",
                }
            )
    return {"workspace_id": workspace_id, "files": files}


@app.get(
    "/api/workspaces/{workspace_id}/raw/{relative_path:path}",
    response_class=PlainTextResponse,
)
def read_file(workspace_id: str, relative_path: str) -> str:
    workspace_root = (DRIVE_ROOT / workspace_id).resolve()
    target_path = (workspace_root / relative_path).resolve()
    if not str(target_path).startswith(str(workspace_root)):
        raise HTTPException(status_code=400, detail="Invalid path.")
    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")
    return target_path.read_text(encoding="utf-8", errors="ignore")


@app.post("/api/workspaces/{workspace_id}/files")
def create_file(workspace_id: str, request: CreateDriveFileRequest) -> dict[str, str]:
    workspace_root = (DRIVE_ROOT / workspace_id).resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)
    target_path = (workspace_root / request.path).resolve()
    if not str(target_path).startswith(str(workspace_root)):
        raise HTTPException(status_code=400, detail="Invalid path.")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(request.content, encoding="utf-8")
    return {"status": "ok", "path": request.path}
