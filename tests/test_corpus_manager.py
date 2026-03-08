from pathlib import Path
from shutil import copyfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bridge"))

from auth import AuthenticatedUser
from config import Settings
from corpus_models import CreateCorpusRequest
from corpus_service import CorpusManagerService
from corpus_store import DuplicateCorpusSlugError
from models import QueryRequest


def make_user(email: str, *, groups: list[str] | None = None, roles: list[str] | None = None) -> AuthenticatedUser:
    return AuthenticatedUser(
        sub=email,
        email=email,
        preferred_username=email,
        groups=groups or [],
        roles=roles or [],
        raw_payload={},
    )


def build_settings(tmp_path: Path) -> Settings:
    template_root = tmp_path / "template"
    template_root.mkdir(parents=True, exist_ok=True)
    copyfile(Path("graphrag/settings.yaml"), template_root / "settings.yaml")
    return Settings(
        bridge_public_url="http://bridge.test",
        openwebui_public_url="http://chat.test",
        keycloak_public_url="http://sso.test",
        keycloak_internal_url="http://sso.test",
        keycloak_realm="openwebui",
        graph_viewer_auth_required=False,
        corpus_manager_public_url="http://corpus.test",
        corpus_manager_auth_required=False,
        corpus_manager_root=tmp_path / "corpus-data",
        graphrag_template_root=template_root,
        openai_api_key="CHANGE_ME",
        openai_api_base="http://llm.test/v1",
        openai_model="demo-model",
    )


def run_all_jobs(service: CorpusManagerService) -> None:
    while service.run_next_job("test-worker"):
        pass


def test_corpus_manager_sync_index_publish_and_query(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "policy.md").write_text("# Policy\nFinance corpus rules.", encoding="utf-8")
    (source_root / "notes.txt").write_text("Quarterly audit reminders.", encoding="utf-8")

    service = CorpusManagerService(build_settings(tmp_path))
    admin = make_user("admin@test.local", roles=["admin"])
    analyst = make_user("analyst@test.local")

    corpus = service.create_corpus(
        CreateCorpusRequest(
            slug="finance-2026",
            name="Finance 2026",
            description="Finance knowledge base",
            source_kind="filesystem",
            source_name="Local filesystem",
            source_config={"path": str(source_root)},
            allowed_users=["analyst@test.local"],
        ),
        admin,
    )
    assert corpus.slug == "finance-2026"

    sync_job = service.queue_sync(corpus.id, analyst)
    assert sync_job.status == "queued"
    run_all_jobs(service)

    corpus = service.get_corpus(corpus.id, analyst)
    assert corpus.versions
    version = corpus.versions[0]
    assert version.status == "snapshot_ready"
    assert version.document_count == 2

    index_job = service.queue_index(corpus.id, analyst, version.id)
    assert index_job.status == "queued"
    run_all_jobs(service)

    corpus = service.get_corpus(corpus.id, analyst)
    version = corpus.versions[0]
    assert version.status == "ready"
    assert corpus.jobs[0].status == "completed"

    publish = service.publish_version(corpus.id, version.id, analyst)
    assert publish.status == "ok"

    query_service, resolved_version = service.resolve_query_service(corpus.id, analyst)
    response = query_service.query(QueryRequest(question="What does the finance corpus contain?", corpus_id=corpus.id))
    assert response.answer
    assert response.graph_url and f"corpus_id={corpus.id}" in response.graph_url
    assert resolved_version["id"] == version.id


def test_corpus_acl_blocks_unauthorized_user(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "secret.md").write_text("# Secret\nRestricted information.", encoding="utf-8")

    service = CorpusManagerService(build_settings(tmp_path))
    owner = make_user("owner@test.local")
    outsider = make_user("outsider@test.local")

    corpus = service.create_corpus(
        CreateCorpusRequest(
            slug="private-corpus",
            name="Private corpus",
            source_kind="filesystem",
            source_name="Local filesystem",
            source_config={"path": str(source_root)},
            allowed_users=["owner@test.local"],
        ),
        owner,
    )

    assert [item.id for item in service.list_corpora(owner)] == [corpus.id]
    assert service.list_corpora(outsider) == []

    try:
        service.get_corpus(corpus.id, outsider)
    except LookupError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Unauthorized user should not see private corpus details.")


def test_group_acl_allows_access_and_notifications(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "ops.md").write_text("# Ops\nPlatform runbooks.", encoding="utf-8")

    service = CorpusManagerService(build_settings(tmp_path))
    admin = make_user("admin@test.local", roles=["admin"])
    operator = make_user("operator@test.local", groups=["ops-team"])

    corpus = service.create_corpus(
        CreateCorpusRequest(
            slug="ops-corpus",
            name="Operations corpus",
            source_kind="filesystem",
            source_name="Local filesystem",
            source_config={"path": str(source_root)},
            allowed_groups=["ops-team"],
        ),
        admin,
    )

    service.queue_sync(corpus.id, admin)
    notifications = service.notifications(operator)
    assert notifications
    assert notifications[0].corpus_id == corpus.id


def test_duplicate_corpus_slug_raises_a_friendly_error(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "doc.md").write_text("# Test\nDuplicate slug coverage.", encoding="utf-8")

    service = CorpusManagerService(build_settings(tmp_path))
    admin = make_user("admin@test.local", roles=["admin"])

    service.create_corpus(
        CreateCorpusRequest(
            slug="shared-slug",
            name="First corpus",
            source_kind="filesystem",
            source_name="Local filesystem",
            source_config={"path": str(source_root)},
        ),
        admin,
    )

    try:
        service.create_corpus(
            CreateCorpusRequest(
                slug="shared-slug",
                name="Second corpus",
                source_kind="filesystem",
                source_name="Local filesystem",
                source_config={"path": str(source_root)},
            ),
            admin,
        )
    except DuplicateCorpusSlugError as error:
        assert error.slug == "shared-slug"
        assert "already exists" in str(error)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Duplicate slugs must raise DuplicateCorpusSlugError.")


def test_delete_corpus_removes_it_from_metadata_and_storage(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "doc.md").write_text("# Ops\nDelete corpus test.", encoding="utf-8")

    service = CorpusManagerService(build_settings(tmp_path))
    owner = make_user("owner@test.local")

    corpus = service.create_corpus(
        CreateCorpusRequest(
            slug="delete-me",
            name="Delete me",
            source_kind="filesystem",
            source_name="Local filesystem",
            source_config={"path": str(source_root)},
            allowed_users=["owner@test.local"],
        ),
        owner,
    )
    service.queue_sync(corpus.id, owner)
    run_all_jobs(service)

    corpus_dir = tmp_path / "corpus-data" / "corpora" / corpus.id
    logs_dir = tmp_path / "corpus-data" / "logs" / corpus.id
    assert corpus_dir.exists()
    assert logs_dir.exists()

    deleted = service.delete_corpus(corpus.id, owner)
    assert deleted.status == "ok"

    assert service.list_corpora(owner) == []
    assert not corpus_dir.exists()
    assert not logs_dir.exists()

    try:
        service.get_corpus(corpus.id, owner)
    except LookupError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("Deleted corpus should no longer be retrievable.")
