"""Auth endpoints — current user profile (Firebase-backed)."""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import UserPublic

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=UserPublic, summary="Current user profile")
async def get_me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        photo_url=current_user.photo_url,
        email_verified=current_user.email_verified,
    )
