from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, verify_password
from app.models import AuditResultStatus, User
from app.schemas.auth import AuthResponse, UserResponse
from app.services.audit_service import log_action


def authenticate_user(db: Session, email: str, password: str) -> AuthResponse:
    query = select(User).options(joinedload(User.role)).where(User.email == email)
    user = db.scalars(query).first()
    if user is None or not verify_password(password, user.hashed_password):
        log_action(
            db,
            user_id=user.id if user else None,
            action_type="auth.login",
            explanation="Failed login attempt",
            success=False,
            result_status=AuditResultStatus.FAILURE,
            details={"email": email},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    log_action(
        db,
        user_id=user.id,
        action_type="auth.login",
        explanation="User logged in",
        result_status=AuditResultStatus.SUCCESS,
        details={"email": user.email, "role": user.role.name.value},
    )
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))
