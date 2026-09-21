from fastapi import APIRouter

from app.api.routes import ask, auth, care_events, care_profiles, chat, wellbeing

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(care_profiles.router, prefix="/care-profiles", tags=["care profiles"])
api_router.include_router(wellbeing.router, prefix="/care-profiles", tags=["wellbeing"])
api_router.include_router(care_events.router, prefix="/care-profiles", tags=["care events"])
api_router.include_router(chat.router, prefix="/care-profiles", tags=["chat"])
api_router.include_router(ask.router, prefix="/care-profiles", tags=["ask care relay"])
