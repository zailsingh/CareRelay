# Phase 4 — CareProfile family group chat

## 1. Chat data model

Chat remains a communication domain, separate from wellbeing self reports and the formal CareEvent record.

Each CareProfile has one default `ChatRoom`. A room is created with every new profile, and migration `20260918_0004` backfills exactly one room for each existing profile. `ChatMessage` stores the room, authenticated sender, text, sent timestamp, and nullable edited/deleted timestamps. Deletion is a sender-only soft delete: the text is cleared and the tombstone remains for ordering and client convergence.

`ChatReadState` stores one high-water mark per room/member. `last_read_message_id` identifies the latest message the member has acknowledged. `ChatAttachment` stores metadata and an opaque storage key only; Phase 4 exposes no upload, download, or filesystem URL API.

CareEvents have an optional `source_chat_message_id`. This is provenance only. It does not merge the models, copy later message edits, or make chat part of the care record.

## 2. REST and WebSocket architecture

The default room is addressed through the profile rather than exposing room selection:

* `GET /api/v1/care-profiles/{id}/chat/messages?limit=&before=` — newest-first cursor page
* `POST /api/v1/care-profiles/{id}/chat/messages` — send text
* `GET /api/v1/care-profiles/{id}/chat/unread` — unread count
* `POST /api/v1/care-profiles/{id}/chat/read` — advance through a supplied message or the latest message
* `DELETE /api/v1/care-profiles/{id}/chat/messages/{message_id}` — soft-delete the sender's own message
* `GET /api/v1/care-profiles/{id}/chat/messages/{message_id}/care-event-draft` — return a non-persisted draft
* `WS /api/v1/care-profiles/{id}/chat/ws?ticket=…` — current realtime signal flow; Phase 5 replaced the original JWT query parameter with a one-time ticket

The cursor encodes the final `(sent_at, id)` pair in the page. Ordering uses both fields so equal timestamps remain deterministic. Deleted messages remain as tombstones in pages. The WebSocket sends `ready`, `message_created`, and `message_deleted` events and answers an optional `ping` with `pong`.

REST and PostgreSQL are the durable source of truth. The mobile client reloads the newest page on every successful WebSocket connection, deduplicates by message ID, and therefore recovers messages missed while offline. The socket is not used to persist client messages.

## 3. Authorization

Every REST operation first uses the existing CareProfile membership dependency. A non-member receives 404, including for message and draft identifiers that exist. Message senders are derived from the access token; no sender ID is accepted from a client. Only the sender may delete a message.

Phase 4 originally decoded the JWT from the socket URL. Phase 5 supersedes this with an authenticated REST exchange for a short-lived, one-time WebSocket ticket; long-lived JWTs are no longer placed in WebSocket URLs.

## 4. Unread model

Unread count includes non-deleted messages from other members after the member's high-water mark. A member's own messages never increase their unread count. Marking an older message cannot move the marker backwards.

Opening Chat loads the unread value and acknowledges the latest displayed message. Realtime arrivals are reflected immediately. When the socket reconnects, the REST recovery request and read-state endpoint reconcile transient client state.

## 5. Chat → CareEvent workflow

Long-pressing a non-deleted message offers **Add to Care Record** to admin, family, and carer memberships. The draft endpoint only returns:

* source chat message ID
* message timestamp as the initial occurrence
* message text as the initial summary
* empty metadata and no selected event type

No CareEvent exists at this point. The mobile review sheet requires the user to choose an event type and review/edit occurrence time, summary, and type-specific structured fields. Only **Confirm and add to care record** calls the CareEvent create API with `confirmation_status=confirmed` and the source reference. The server rejects a chat-linked event that is not explicitly confirmed and rejects a source message from another profile.

No inference, keyword mapping, or AI interpretation occurs. Deleting the original chat message later does not delete or modify the already-confirmed CareEvent.

## 6. Realtime limitations

Fan-out uses an in-process connection manager keyed by CareProfile ID. This is appropriate for the current single API instance and introduces no Redis dependency. Connections are lost on API restart, while messages remain durable and are recovered through REST.

If multiple API instances are introduced, the connection-manager boundary must be backed by authenticated cross-instance pub/sub (for example Redis). Presence, typing indicators, push notifications, delivery receipts, reactions, attachments, and background delivery remain outside Phase 4.

## 7. Test results

* Backend pytest: 45 passed, including membership isolation, unread/read behavior, pagination, WebSocket authentication/delivery, reconnect recovery, conversion confirmation, and independent deletion
* Backend Ruff: passed for app, tests, and migrations
* SQLite Phase 3 → Phase 4 upgrade, schema drift, downgrade, and re-upgrade: passed
* PostgreSQL 17 Phase 3 → Phase 4 upgrade, schema drift, downgrade, and re-upgrade: passed
* Containerized backend pytest: 45 passed
* Runtime health, profile creation, chat send/list, and unread API checks: passed
* Mobile Jest: 9 passed across 5 suites
* Mobile TypeScript: passed
* Expo SDK dependency compatibility check: passed
* Expo iOS production export: passed

## 8. Phase 5 considerations

* Chat text is private communication, not formal evidence and not automatically a CareEvent.
* Any future AI-assisted conversion must preserve the current non-persisted draft and explicit human confirmation boundary.
* `source_chat_message_id` is provenance. AI outputs should add their own transparent provenance rather than overloading this field.
* Multi-instance deployment requires shared fan-out before horizontally scaling the API.
* Attachment rows are metadata-only scaffolding. A future implementation needs private object storage, authorization-gated downloads, malware/content controls, retention rules, and no public filesystem paths.
* Message editing is represented in the schema but has no Phase 4 endpoint or UI.
* There are no push notifications, background message delivery, AI/LLM calls, voice transcription, OCR, medication schedules, billing, or external health integrations.
