from fastapi import APIRouter

from app.api.routes import (
    ask,
    auth,
    care_events,
    care_profiles,
    chat,
    invitations,
    medications,
    reports,
    wellbeing,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(care_profiles.router, prefix="/care-profiles", tags=["care profiles"])
api_router.include_router(wellbeing.router, prefix="/care-profiles", tags=["wellbeing"])
api_router.include_router(care_events.router, prefix="/care-profiles", tags=["care events"])
api_router.include_router(chat.router, prefix="/care-profiles", tags=["chat"])
api_router.include_router(ask.router, prefix="/care-profiles", tags=["ask care relay"])
api_router.include_router(medications.router, prefix="/care-profiles", tags=["medications"])
api_router.include_router(reports.router, prefix="/care-profiles", tags=["care reports"])
api_router.include_router(invitations.router, tags=["care invitations"])
