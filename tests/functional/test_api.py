import requests


def test_bridge_healthz(bridge_base_url: str) -> None:
    response = requests.get(f"{bridge_base_url}/healthz", timeout=30)
    response.raise_for_status()
    data = response.json()
    assert data["status"] == "ok"
    assert "index_present" in data


def test_bridge_query_returns_answer(bridge_base_url: str) -> None:
    response = requests.post(
        f"{bridge_base_url}/query",
        json={"question": "What is the role of the bridge service?"},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    assert data["answer"]
    assert data["engine_used"] in {
        "graphrag-cli",
        "external-openai-compatible",
        "local-deterministic",
    }
    assert "graph_url" in data


def test_graph_page_is_reachable(bridge_base_url: str) -> None:
    response = requests.get(f"{bridge_base_url}/graph", timeout=30)
    response.raise_for_status()
    assert "Visualiseur GraphRAG" in response.text
    assert "/assets/favicon-32x32.png" in response.text
    assert "/assets/mirai-graphrag-256.png" in response.text
    assert "Relancer dans le chat" in response.text
    assert "Synthèse en cours" in response.text
    assert "Télécharger les fragments sélectionnés" in response.text
    assert "<textarea" in response.text


def test_graph_assets_are_reachable(bridge_base_url: str) -> None:
    favicon_response = requests.get(f"{bridge_base_url}/favicon.ico", timeout=30)
    favicon_response.raise_for_status()
    assert favicon_response.headers["content-type"].startswith("image/")

    hero_response = requests.get(f"{bridge_base_url}/assets/mirai-graphrag-256.png", timeout=30)
    hero_response.raise_for_status()
    assert hero_response.headers["content-type"].startswith("image/")


def test_graph_config_endpoint_returns_auth_mode(bridge_base_url: str) -> None:
    response = requests.get(f"{bridge_base_url}/graph/config", timeout=30)
    response.raise_for_status()
    data = response.json()
    assert "auth_required" in data
    assert "client_id" in data
    assert "openwebui_url" in data


def test_graph_data_requires_auth_when_enabled(bridge_base_url: str) -> None:
    config_response = requests.get(f"{bridge_base_url}/graph/config", timeout=30)
    config_response.raise_for_status()
    config = config_response.json()

    response = requests.get(
        f"{bridge_base_url}/graph/data",
        params={"query": "Bretigny Troyes", "max_nodes": 40},
        timeout=60,
    )
    if config.get("auth_required"):
        assert response.status_code == 401
        return

    response.raise_for_status()
    data = response.json()
    assert "graph_ready" in data
    assert "nodes" in data
    assert "edges" in data
