from enum import StrEnum


class CareRole(StrEnum):
    ADMIN = "admin"
    FAMILY = "family"
    CARER = "carer"
    CARED_PERSON = "cared_person"


class SymptomKind(StrEnum):
    DIZZINESS = "dizziness"
    FATIGUE = "fatigue"
    PAIN = "pain"
    WEAKNESS = "weakness"
    NAUSEA = "nausea"
    BREATHLESSNESS = "breathlessness"
    POOR_SLEEP = "poor_sleep"
    LOW_APPETITE = "low_appetite"
    FEELING_GOOD = "feeling_good"
    OTHER = "other"


class CareEventType(StrEnum):
    FAMILY_OBSERVATION = "family_observation"
    SYMPTOM_OBSERVATION = "symptom_observation"
    MEDICATION_TAKEN = "medication_taken"
    MEDICATION_MISSED = "medication_missed"
    MEDICATION_SKIPPED = "medication_skipped"
    FALL = "fall"
    ACTIVITY = "activity"
    SLEEP_OBSERVATION = "sleep_observation"
    APPOINTMENT = "appointment"
    GENERAL_NOTE = "general_note"


class CareEventSource(StrEnum):
    ADMIN = "admin"
    FAMILY = "family"
    CARER = "carer"
    SUBJECT = "subject"


class ConfirmationStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class AuditAction(StrEnum):
    CARE_PROFILE_CREATED = "care_profile_created"
    INITIAL_ADMIN_CREATED = "initial_admin_created"
    SUBJECT_CHANGED = "subject_changed"
    TIMEZONE_CHANGED = "timezone_changed"
    CARE_EVENT_CREATED = "care_event_created"
    CARE_EVENT_UPDATED = "care_event_updated"
    CARE_EVENT_DELETED = "care_event_deleted"
    MEDICATION_CREATED = "medication_created"
    MEDICATION_UPDATED = "medication_updated"
    MEDICATION_DEACTIVATED = "medication_deactivated"
    MEDICATION_SCHEDULE_CREATED = "medication_schedule_created"
    MEDICATION_SCHEDULE_UPDATED = "medication_schedule_updated"
    MEDICATION_SCHEDULE_REMOVED = "medication_schedule_removed"
    MEDICATION_DOSE_RECORDED = "medication_dose_recorded"
    MEDICATION_DOSE_CORRECTED = "medication_dose_corrected"
    REPORT_PREVIEW_GENERATED = "report_preview_generated"
    REPORT_PDF_GENERATED = "report_pdf_generated"
    INVITATION_CREATED = "invitation_created"
    INVITATION_EMAIL_SENT = "invitation_email_sent"
    INVITATION_EMAIL_DELIVERY_FAILED = "invitation_email_delivery_failed"
    INVITATION_RESENT = "invitation_resent"
    INVITATION_REVOKED = "invitation_revoked"
    INVITATION_ACCEPTED = "invitation_accepted"
    MEMBERSHIP_CREATED = "membership_created"
    MEMBERSHIP_ROLE_CHANGED = "membership_role_changed"
    MEMBERSHIP_REMOVED = "membership_removed"
    SUBJECT_LINKED = "subject_linked"
    ACCOUNT_DELETION_REQUESTED = "account_deletion_requested"


class MedicationScheduleType(StrEnum):
    SCHEDULED = "scheduled"
    AS_NEEDED = "as_needed"


class MedicationDoseStatus(StrEnum):
    TAKEN = "taken"
    MISSED = "missed"
    SKIPPED = "skipped"
