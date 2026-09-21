import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth, login


def create_profile(client: TestClient, token: str, name: str = "Mum") -> dict[str, object]:
    response = client.post(
        "/api/v1/care-profiles",
        headers=auth(token),
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_creator_becomes_admin_and_profile_is_listed(client: TestClient) -> None:
    token = login(client, "alex@example.com", "Alex")
    profile = create_profile(client, token)
    assert profile["role"] == "admin"

    response = client.get("/api/v1/care-profiles", headers=auth(token))
    assert response.status_code == 200
    assert response.json() == [profile]


def test_profile_name_cannot_be_blank(client: TestClient) -> None:
    token = login(client, "alex@example.com", "Alex")
    response = client.post(
        "/api/v1/care-profiles",
        headers=auth(token),
        json={"name": "   "},
    )
    assert response.status_code == 422


def test_non_member_cannot_discover_profile(client: TestClient) -> None:
    owner = login(client, "owner@example.com", "Owner")
    outsider = login(client, "outsider@example.com", "Outsider")
    profile = create_profile(client, owner)

    profile_response = client.get(f"/api/v1/care-profiles/{profile['id']}", headers=auth(outsider))
    members_response = client.get(
        f"/api/v1/care-profiles/{profile['id']}/members", headers=auth(outsider)
    )
    assert profile_response.status_code == 404
    assert members_response.status_code == 404


@pytest.mark.parametrize("role", ["family", "carer", "cared_person"])
def test_admin_can_add_every_supported_role(client: TestClient, role: str) -> None:
    owner = login(client, "owner@example.com", "Owner")
    member_email = f"{role}@example.com"
    member = login(client, member_email, role.replace("_", " ").title())
    profile = create_profile(client, owner)

    add_response = client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner),
        json={"email": member_email, "role": role},
    )
    assert add_response.status_code == 201, add_response.text
    assert add_response.json()["role"] == role

    read_response = client.get(f"/api/v1/care-profiles/{profile['id']}", headers=auth(member))
    assert read_response.status_code == 200
    assert read_response.json()["role"] == role


def test_non_admin_cannot_add_members(client: TestClient) -> None:
    owner = login(client, "owner@example.com", "Owner")
    family = login(client, "family@example.com", "Family")
    login(client, "other@example.com", "Other")
    profile = create_profile(client, owner)

    client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner),
        json={"email": "family@example.com", "role": "family"},
    )
    response = client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(family),
        json={"email": "other@example.com", "role": "carer"},
    )
    assert response.status_code == 403
