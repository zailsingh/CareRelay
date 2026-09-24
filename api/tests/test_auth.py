from fastapi.testclient import TestClient

from tests.conftest import auth, login


def test_dev_login_creates_and_reuses_user(client: TestClient) -> None:
    token = login(client, "Casey@Example.com", "Casey")
    first = client.get("/api/v1/auth/me", headers=auth(token))
    assert first.status_code == 200
    assert first.json()["email"] == "casey@example.com"

    second_token = login(client, "casey@example.com", "Casey Updated")
    second = client.get("/api/v1/auth/me", headers=auth(second_token))
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["display_name"] == "Casey Updated"


def test_protected_endpoint_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/care-profiles")
    assert response.status_code == 401


def test_dev_login_rejects_blank_display_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/dev-login",
        json={"email": "blank@example.com", "display_name": "   "},
    )
    assert response.status_code == 422


def test_apple_endpoint_is_present_but_unconfigured(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/apple",
        json={"identity_token": "example-token", "nonce": "n" * 32},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Apple Sign-In is not configured"


def test_apple_endpoint_requires_identity_token_and_nonce(client: TestClient) -> None:
    missing_token = client.post("/api/v1/auth/apple", json={"nonce": "n" * 32})
    missing_nonce = client.post("/api/v1/auth/apple", json={"identity_token": "example-token"})
    assert missing_token.status_code == 422
    assert missing_nonce.status_code == 422
