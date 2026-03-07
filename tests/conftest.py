import os

import pytest


@pytest.fixture(scope="session")
def bridge_base_url() -> str:
    return os.getenv("BRIDGE_BASE_URL", "http://localhost:8081")


@pytest.fixture(scope="session")
def openwebui_base_url() -> str:
    return os.getenv("OPENWEBUI_BASE_URL", "http://localhost:3000")

