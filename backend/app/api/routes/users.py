from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db, require_roles
from app.models import RoleName, User
from app.schemas.auth import RoleResponse, UserLocaleUpdateRequest, UserResponse
from app.services.user_service import list_roles, list_users, update_user_locale


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
def patch_me(
    payload: UserLocaleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    return UserResponse.model_validate(update_user_locale(db, current_user, payload.locale))


@router.get("", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(get_db), _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN))
) -> list[UserResponse]:
    return [UserResponse.model_validate(user) for user in list_users(db)]


@router.get("/roles", response_model=list[RoleResponse])
def get_roles(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[RoleResponse]:
    return [RoleResponse.model_validate(role) for role in list_roles(db)]
