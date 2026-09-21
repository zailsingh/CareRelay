from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.services.websocket_tickets import WebSocketTicketStore
from tests.conftest import auth, login


def setup_chat_profile(client: TestClient, suffix: str = "") -> dict[str, Any]:
    owner = login(client, f"owner{suffix}@example.com", f"Owner {suffix}".strip())
    family = login(client, f"family{suffix}@example.com", f"Sarah {suffix}".strip())
    profile_response = client.post(
        "/api/v1/care-profiles",
        headers=auth(owner),
        json={"name": f"Family {suffix}".strip(), "timezone": "Australia/Melbourne"},
    )
    assert profile_response.status_code == 201, profile_response.text
    profile = profile_response.json()
    member_response = client.post(
        f"/api/v1/care-profiles/{profile['id']}/members",
        headers=auth(owner),
        json={"email": f"family{suffix}@example.com", "role": "family"},
    )
    assert member_response.status_code == 201, member_response.text
    return {"profile": profile, "owner": owner, "family": family}


def send_message(client: TestClient, profile_id: str, token: str, body: str):
    return client.post(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(token),
        json={"body": body},
    )


def test_members_can_send_and_read_messages(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    created = send_message(client, profile_id, context["family"], "How was lunch?")
    assert created.status_code == 201, created.text
    assert created.json()["sender"]["display_name"] == "Sarah"
    assert created.json()["is_deleted"] is False

    page = client.get(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(context["owner"]),
    )
    assert page.status_code == 200
    assert [item["body"] for item in page.json()["items"]] == ["How was lunch?"]


def test_non_members_get_404_and_profiles_are_isolated(client: TestClient) -> None:
    first = setup_chat_profile(client, "-one")
    second = setup_chat_profile(client, "-two")
    first_id = first["profile"]["id"]
    second_id = second["profile"]["id"]
    send_message(client, first_id, first["owner"], "Only profile one can see this")

    assert (
        client.get(
            f"/api/v1/care-profiles/{first_id}/chat/messages",
            headers=auth(second["owner"]),
        ).status_code
        == 404
    )
    assert send_message(client, first_id, second["owner"], "Intrusion").status_code == 404
    assert (
        client.post(
            f"/api/v1/care-profiles/{first_id}/chat/ws-ticket",
            headers=auth(second["owner"]),
        ).status_code
        == 404
    )
    second_messages = client.get(
        f"/api/v1/care-profiles/{second_id}/chat/messages",
        headers=auth(second["owner"]),
    ).json()["items"]
    assert second_messages == []


def test_unread_count_and_read_marker_do_not_regress(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    first = send_message(client, profile_id, context["family"], "First").json()
    second = send_message(client, profile_id, context["family"], "Second").json()
    send_message(client, profile_id, context["owner"], "My own message")

    unread_url = f"/api/v1/care-profiles/{profile_id}/chat/unread"
    assert client.get(unread_url, headers=auth(context["owner"])).json() == {"unread_count": 2}
    read_url = f"/api/v1/care-profiles/{profile_id}/chat/read"
    marked = client.post(
        read_url,
        headers=auth(context["owner"]),
        json={"through_message_id": second["id"]},
    )
    assert marked.json() == {"unread_count": 0}
    client.post(
        read_url,
        headers=auth(context["owner"]),
        json={"through_message_id": first["id"]},
    )
    assert client.get(unread_url, headers=auth(context["owner"])).json() == {"unread_count": 0}
    send_message(client, profile_id, context["family"], "Third")
    assert client.get(unread_url, headers=auth(context["owner"])).json() == {"unread_count": 1}


def test_cursor_pagination_returns_newest_first_without_overlap(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    for number in range(5):
        response = send_message(client, profile_id, context["owner"], f"Message {number}")
        assert response.status_code == 201

    url = f"/api/v1/care-profiles/{profile_id}/chat/messages"
    first = client.get(url, headers=auth(context["owner"]), params={"limit": 2}).json()
    second = client.get(
        url,
        headers=auth(context["owner"]),
        params={"limit": 2, "before": first["next_cursor"]},
    ).json()
    third = client.get(
        url,
        headers=auth(context["owner"]),
        params={"limit": 2, "before": second["next_cursor"]},
    ).json()
    bodies = [item["body"] for page in (first, second, third) for item in page["items"]]
    assert bodies == [f"Message {number}" for number in reversed(range(5))]
    assert len({item["id"] for page in (first, second, third) for item in page["items"]}) == 5
    assert third["next_cursor"] is None
    assert (
        client.get(url, headers=auth(context["owner"]), params={"before": "bad"}).status_code == 422
    )


def test_websocket_auth_delivery_and_rest_recovery(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    with pytest.raises(WebSocketDisconnect) as invalid:
        with client.websocket_connect(
            f"/api/v1/care-profiles/{profile_id}/chat/ws?ticket=invalid"
        ) as socket:
            socket.receive_json()
    assert invalid.value.code == 4401

    ticket_response = client.post(
        f"/api/v1/care-profiles/{profile_id}/chat/ws-ticket",
        headers=auth(context["owner"]),
    )
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]

    with client.websocket_connect(
        f"/api/v1/care-profiles/{profile_id}/chat/ws?ticket={ticket}"
    ) as socket:
        assert socket.receive_json()["type"] == "ready"
        sent = send_message(client, profile_id, context["family"], "Realtime")
        assert sent.status_code == 201
        event = socket.receive_json()
        assert event["type"] == "message_created"
        assert event["message"]["body"] == "Realtime"

    with pytest.raises(WebSocketDisconnect) as reused:
        with client.websocket_connect(
            f"/api/v1/care-profiles/{profile_id}/chat/ws?ticket={ticket}"
        ) as socket:
            socket.receive_json()
    assert reused.value.code == 4401

    # The WebSocket is only a signal channel. A reconnect recovers missed data via REST.
    missed = send_message(client, profile_id, context["family"], "Sent while disconnected").json()
    recovered = client.get(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(context["owner"]),
    ).json()["items"]
    assert recovered[0]["id"] == missed["id"]


def test_chat_conversion_is_a_reviewed_separate_record(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    message = send_message(
        client,
        profile_id,
        context["family"],
        "Mum walked around the garden.",
    ).json()
    events_url = f"/api/v1/care-profiles/{profile_id}/care-events"
    draft = client.get(
        f"/api/v1/care-profiles/{profile_id}/chat/messages/{message['id']}/care-event-draft",
        headers=auth(context["family"]),
    )
    assert draft.status_code == 200
    assert draft.json()["event_type"] is None
    assert draft.json()["summary"] == "Mum walked around the garden."
    assert client.get(events_url, headers=auth(context["family"])).json() == []

    unconfirmed = client.post(
        events_url,
        headers=auth(context["family"]),
        json={
            "event_type": "activity",
            "occurred_at": draft.json()["occurred_at"],
            "summary": draft.json()["summary"],
            "metadata": {"activity": "walking"},
            "confirmation_status": "unconfirmed",
            "source_chat_message_id": message["id"],
        },
    )
    assert unconfirmed.status_code == 422

    confirmed = client.post(
        events_url,
        headers=auth(context["family"]),
        json={
            "event_type": "activity",
            "occurred_at": draft.json()["occurred_at"],
            "summary": draft.json()["summary"],
            "metadata": {"activity": "walking", "duration_minutes": 15},
            "confirmation_status": "confirmed",
            "source_chat_message_id": message["id"],
        },
    )
    assert confirmed.status_code == 201, confirmed.text
    assert confirmed.json()["source_chat_message_id"] == message["id"]

    deleted = client.delete(
        f"/api/v1/care-profiles/{profile_id}/chat/messages/{message['id']}",
        headers=auth(context["family"]),
    )
    assert deleted.status_code == 204
    events = client.get(events_url, headers=auth(context["owner"])).json()
    assert len(events) == 1
    assert events[0]["summary"] == "Mum walked around the garden."
    assert events[0]["source_chat_message_id"] == message["id"]


def test_only_sender_can_delete_message(client: TestClient) -> None:
    context = setup_chat_profile(client)
    profile_id = context["profile"]["id"]
    message = send_message(client, profile_id, context["family"], "Private wording").json()
    url = f"/api/v1/care-profiles/{profile_id}/chat/messages/{message['id']}"
    assert client.delete(url, headers=auth(context["owner"])).status_code == 403
    assert client.delete(url, headers=auth(context["family"])).status_code == 204
    tombstone = client.get(
        f"/api/v1/care-profiles/{profile_id}/chat/messages",
        headers=auth(context["owner"]),
    ).json()["items"][0]
    assert tombstone["body"] is None
    assert tombstone["is_deleted"] is True


def test_websocket_ticket_expires_and_is_one_time() -> None:
    from uuid import uuid4

    store = WebSocketTicketStore(ttl_seconds=-1)
    ticket = store.issue(uuid4(), uuid4())
    assert store.consume(ticket.value, ticket.care_profile_id) is None

    store = WebSocketTicketStore(ttl_seconds=45)
    ticket = store.issue(uuid4(), uuid4())
    assert store.consume(ticket.value, uuid4()) is None
    assert store.consume(ticket.value, ticket.care_profile_id) is None
