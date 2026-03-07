import logging
import sys
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import PLACEHOLDER_VALUES, get_settings

LOGGER = logging.getLogger("graphrag.cache_sync")


def _normalize_prefix(prefix: str) -> str:
    cleaned = prefix.strip().strip("/")
    return cleaned


class S3CacheSync:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_dir = self.settings.graphrag_cache_dir
        self.bucket = self.settings.graphrag_cache_s3_bucket.strip()
        self.prefix = _normalize_prefix(self.settings.graphrag_cache_s3_prefix)

    @property
    def enabled(self) -> bool:
        if not self.settings.graphrag_cache_s3_enabled:
            return False
        return self.bucket not in PLACEHOLDER_VALUES

    def _client(self):
        kwargs: dict[str, str] = {}
        if self.settings.graphrag_cache_s3_region:
            kwargs["region_name"] = self.settings.graphrag_cache_s3_region
        if self.settings.graphrag_cache_s3_endpoint_url:
            kwargs["endpoint_url"] = self.settings.graphrag_cache_s3_endpoint_url
        if self.settings.graphrag_cache_s3_access_key_id:
            kwargs["aws_access_key_id"] = self.settings.graphrag_cache_s3_access_key_id
        if self.settings.graphrag_cache_s3_secret_access_key:
            kwargs["aws_secret_access_key"] = (
                self.settings.graphrag_cache_s3_secret_access_key
            )
        if self.settings.graphrag_cache_s3_session_token:
            kwargs["aws_session_token"] = self.settings.graphrag_cache_s3_session_token
        return boto3.client("s3", **kwargs)

    def _key_for(self, relative_path: Path) -> str:
        relative = relative_path.as_posix().lstrip("/")
        return f"{self.prefix}/{relative}" if self.prefix else relative

    def pull(self) -> int:
        if not self.enabled:
            LOGGER.info("S3 cache sync disabled; skipping pull.")
            return 0

        self.local_dir.mkdir(parents=True, exist_ok=True)
        client = self._client()
        downloaded = 0
        try:
            paginator = client.get_paginator("list_objects_v2")
            prefix = f"{self.prefix}/" if self.prefix else ""
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    relative = key[len(prefix) :] if prefix else key
                    if not relative or key.endswith("/"):
                        continue
                    destination = self.local_dir / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    client.download_file(self.bucket, key, str(destination))
                    downloaded += 1
        except (BotoCoreError, ClientError) as exc:
            LOGGER.exception("Failed to pull GraphRAG cache from S3.")
            raise SystemExit(str(exc)) from exc

        LOGGER.info(
            "Pulled %s GraphRAG cache object(s) from s3://%s/%s",
            downloaded,
            self.bucket,
            self.prefix,
        )
        return 0

    def push(self) -> int:
        if not self.enabled:
            LOGGER.info("S3 cache sync disabled; skipping push.")
            return 0

        self.local_dir.mkdir(parents=True, exist_ok=True)
        client = self._client()
        uploaded = 0
        try:
            for path in sorted(self.local_dir.rglob("*")):
                if not path.is_file():
                    continue
                key = self._key_for(path.relative_to(self.local_dir))
                client.upload_file(str(path), self.bucket, key)
                uploaded += 1
        except (BotoCoreError, ClientError) as exc:
            LOGGER.exception("Failed to push GraphRAG cache to S3.")
            raise SystemExit(str(exc)) from exc

        LOGGER.info(
            "Pushed %s GraphRAG cache object(s) to s3://%s/%s",
            uploaded,
            self.bucket,
            self.prefix,
        )
        return 0


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if len(argv) != 2 or argv[1] not in {"pull", "push"}:
        print("Usage: python cache_sync.py [pull|push]", file=sys.stderr)
        return 2

    sync = S3CacheSync()
    if argv[1] == "pull":
        return sync.pull()
    return sync.push()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
