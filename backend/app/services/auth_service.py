from app.core.exceptions import AuthenticationError, ConflictError, UpstreamError
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import create_access_token, hash_password, needs_rehash, verify_password
from app.models import AuditResultStatus, Role, RoleName, User
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
        raise AuthenticationError("Invalid credentials")

    # SHA-256 → bcrypt opportunistic upgrade. Kullanıcı şifresini değiştirmek
    # zorunda kalmadan otomatik geçer; ilk başarılı login sonrası hash güçlenir.
    if needs_rehash(user.hashed_password):
        try:
            user.hashed_password = hash_password(password)
            db.commit()
        except Exception:  # noqa: BLE001 — upgrade başarısızsa login'i bozma
            db.rollback()

    token = create_access_token(str(user.id), organization_id=user.organization_id)
    log_action(
        db,
        user_id=user.id,
        organization_id=user.organization_id,
        action_type="auth.login",
        explanation="User logged in",
        result_status=AuditResultStatus.SUCCESS,
        details={"email": user.email, "role": user.role.name.value},
    )
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))


def register_customer(db: Session, full_name: str, email: str, password: str, locale: str = "tr") -> AuthResponse:
    existing = db.scalars(select(User).where(User.email == email)).first()
    if existing:
        raise ConflictError("Bu e-posta adresi zaten kayıtlı")

    customer_role = db.scalars(select(Role).where(Role.name == RoleName.CUSTOMER)).first()
    if not customer_role:
        # Sistem konfigürasyon hatası — operatöre kapanmış customer rolüne işaret.
        raise UpstreamError("Customer role not found")

    user = User(
        full_name=full_name.strip(),
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        locale=locale,
        role_id=customer_role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(str(user.id), organization_id=user.organization_id)
    log_action(
        db,
        user_id=user.id,
        organization_id=user.organization_id,
        action_type="auth.register",
        explanation="New customer registered",
        result_status=AuditResultStatus.SUCCESS,
        details={"email": user.email},
    )
    return AuthResponse(access_token=token, user=UserResponse.model_validate(user))
