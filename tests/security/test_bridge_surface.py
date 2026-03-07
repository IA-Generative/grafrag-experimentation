import requests


def test_config_endpoint_does_not_expose_raw_api_key(bridge_base_url: str) -> None:
    response = requests.get(f"{bridge_base_url}/config", timeout=30)
    response.raise_for_status()
    data = response.json()
    assert "openai_api_key" not in data
    assert "openai_api_key_configured" in data


def test_query_endpoint_handles_injection_like_input(bridge_base_url: str) -> None:
    response = requests.post(
        f"{bridge_base_url}/query",
        json={"question": "' OR 1=1; DROP TABLE graph; --"},
        timeout=60,
    )
    assert response.status_code in {200, 422}

