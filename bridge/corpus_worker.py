import os
import time

from corpus_service import CorpusManagerService, default_worker_id
from config import get_settings


def main() -> int:
    settings = get_settings()
    service = CorpusManagerService(settings)
    worker_id = os.getenv("CORPUS_WORKER_ID", default_worker_id())
    poll_seconds = int(os.getenv("CORPUS_WORKER_POLL_SECONDS", "5"))
    run_once = os.getenv("CORPUS_WORKER_ONCE", "false").strip().lower() == "true"

    while True:
        processed = service.run_next_job(worker_id)
        if run_once:
            return 0
        if not processed:
            time.sleep(max(1, poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
