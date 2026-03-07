import requests


def test_openwebui_is_reachable(openwebui_base_url: str) -> None:
    response = requests.get(openwebui_base_url, timeout=30, allow_redirects=True)
    assert response.status_code < 500

