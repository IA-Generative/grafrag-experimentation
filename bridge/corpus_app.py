from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse

from auth import AuthenticatedUser, get_corpus_manager_auth
from config import get_settings
from corpus_models import ActionResponse, CorpusDetail, CorpusManagerConfigResponse, CorpusSummary, CreateCorpusRequest, JobSummary, MeResponse
from corpus_service import CorpusManagerService
from corpus_store import DuplicateCorpusSlugError

settings = get_settings()
manager_auth = get_corpus_manager_auth()
service = CorpusManagerService(settings)
HTML_PATH = Path(__file__).with_name("corpus_manager.html")

app = FastAPI(title="Corpus Manager", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def root() -> str:
    html = HTML_PATH.read_text(encoding="utf-8")
    return html.replace(
        "__CORPUS_MANAGER_CONFIG__",
        service.manager_config().model_dump_json(),
    )


@app.get("/api/config", response_model=CorpusManagerConfigResponse)
def config() -> CorpusManagerConfigResponse:
    return service.manager_config()


@app.get("/api/me", response_model=MeResponse)
def me(user: AuthenticatedUser = Depends(manager_auth.require_user)) -> MeResponse:
    return service.me(user)


@app.get("/api/corpora", response_model=list[CorpusSummary])
def list_corpora(
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> list[CorpusSummary]:
    return service.list_corpora(user)


@app.post("/api/corpora", response_model=CorpusDetail)
def create_corpus(
    request: CreateCorpusRequest,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> CorpusDetail:
    try:
        return service.create_corpus(request, user)
    except DuplicateCorpusSlugError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/corpora/{corpus_id}", response_model=CorpusDetail)
def get_corpus(
    corpus_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> CorpusDetail:
    try:
        return service.get_corpus(corpus_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Corpus not found.") from error


@app.delete("/api/corpora/{corpus_id}", response_model=ActionResponse)
def delete_corpus(
    corpus_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.delete_corpus(corpus_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Corpus not found.") from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/corpora/{corpus_id}/sync", response_model=ActionResponse)
def queue_sync(
    corpus_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.queue_sync(corpus_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Corpus not found.") from error


@app.post("/api/corpora/{corpus_id}/index", response_model=ActionResponse)
def queue_index(
    corpus_id: str,
    version_id: str | None = None,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.queue_index(corpus_id, user, version_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Corpus not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/corpora/{corpus_id}/publish/{version_id}", response_model=ActionResponse)
def publish_version(
    corpus_id: str,
    version_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.publish_version(corpus_id, version_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Version not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/corpora/{corpus_id}/rollback/{version_id}", response_model=ActionResponse)
def rollback_version(
    corpus_id: str,
    version_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.rollback_version(corpus_id, version_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Version not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/corpora/{corpus_id}/jobs", response_model=list[JobSummary])
def list_jobs(
    corpus_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> list[JobSummary]:
    try:
        return service.list_jobs(corpus_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Corpus not found.") from error


@app.get("/api/jobs/{job_id}", response_model=JobSummary)
def get_job(
    job_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> JobSummary:
    try:
        return service.get_job(job_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Job not found.") from error


@app.get("/api/jobs/{job_id}/logs", response_class=PlainTextResponse)
def get_job_logs(
    job_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> str:
    try:
        return service.get_job_logs(job_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Job not found.") from error


@app.post("/api/jobs/{job_id}/retry", response_model=ActionResponse)
def retry_job(
    job_id: str,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> ActionResponse:
    try:
        return service.retry_job(job_id, user)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Job not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/notifications")
def notifications(
    corpus_id: str | None = None,
    user: AuthenticatedUser = Depends(manager_auth.require_user),
) -> list[dict[str, object]]:
    return [item.model_dump() for item in service.notifications(user, corpus_id)]
