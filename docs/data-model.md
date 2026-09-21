# CareRelay data model

```text
User 1 ---- * CareMembership * ---- 1 CareProfile
  |                                      |
  +-- created profiles ------------------+
```

## User

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `email` | varchar(320) | Normalized lowercase, unique |
| `display_name` | varchar(120) | User-facing name |
| `apple_subject` | varchar(255), nullable | Stable Apple identity subject, unique |
| `created_at` | timestamptz | Server generated |

## CareProfile

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key and future tenancy key |
| `name` | varchar(120) | Human-friendly cared-person/profile name |
| `subject_user_id` | UUID, nullable | Canonical cared-for person; must be a member |
| `timezone` | varchar(100) | Valid persisted IANA timezone |
| `created_by_id` | UUID | Required reference to `User` |
| `created_at` | timestamptz | Server generated |

Creating a profile atomically creates an administrator membership for its creator.

## CareMembership

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | Primary key |
| `care_profile_id` | UUID | Cascading reference to `CareProfile` |
| `user_id` | UUID | Cascading reference to `User` |
| `role` | string enum | `admin`, `family`, `carer`, or `cared_person` |
| `created_at` | timestamptz | Server generated |

The pair `(care_profile_id, user_id)` is unique. Both foreign-key directions are indexed for authorization lookups. Role values are constrained in the database as well as in API validation.

## Phase 2: WellbeingCheckin

Each check-in belongs to one care profile and records the authenticated cared person's user ID, a database-constrained 0–100 score, timezone-aware occurrence time, optional note, reserved voice transcript, and creation/update timestamps. Multiple rows can occur on the same day.

## Phase 2: WellbeingSymptom

Symptoms are normalized child rows with a closed enum kind and a unique `(checkin_id, kind)` pair. Deleting a check-in cascades to its symptoms.

## Phase 3: CareEvent

Care Events are family/carer observations stored separately from wellbeing self reports. They include a validated event type, occurrence, authenticated author, server-derived source, factual summary, strict type-specific metadata, confirmation status, and audit timestamps.

Medication taken/missed values are event types only; there is no medication schedule domain.

## Phase 3: AuditLog

Append-only application audit rows capture subject/timezone changes and CareEvent creation, update, or deletion. Audit data has no normal mutation API.

## Phase 4: ChatRoom and ChatMessage

Every CareProfile has one default ChatRoom. ChatMessage stores the authenticated sender, text, deterministic sent timestamp, and optional edit/delete timestamps. Sender deletion clears text but retains a tombstone. Chat is communication and remains separate from CareEvent and WellbeingCheckin.

## Phase 4: ChatReadState

One row per room/member stores a monotonic last-read message marker. Unread counts include only later, non-deleted messages from other members.

## Phase 4: ChatAttachment

Attachment metadata reserves a private opaque storage key, filename, media type, and byte size. Phase 4 has no attachment API and never exposes the storage key or a filesystem URL.

## Phase 4: chat-sourced CareEvent

`CareEvent.source_chat_message_id` is nullable provenance linking an explicitly confirmed record to its originating message. It does not merge the records. Soft-deleting a message leaves the confirmed CareEvent unchanged.

## Phase 5: AskAudit

Minimal AI audit metadata records the profile, actor, SHA-256 question hash, provider/model, tool names, evidence count, success/failure status, optional error code, and timestamp. Raw questions, model prompts, answers, credentials, and chain-of-thought are deliberately not persisted.
