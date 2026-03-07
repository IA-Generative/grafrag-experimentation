from config import get_settings
from models import IndexRequest
from service import GraphRAGService


def main() -> int:
    result = GraphRAGService(get_settings()).index(
        IndexRequest(rebuild=True, strict=True)
    )
    print(result.model_dump_json())
    return 0 if result.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
