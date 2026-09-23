from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    id: UUID
    email: EmailStr | None
    display_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
