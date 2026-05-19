from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import SessionLocal
from app.models import Organization, RoleName, User


security = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user = db.scalars(
        select(User)
        .options(joinedload(User.role))
        .where(User.id == int(payload["sub"]))
    ).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not available")
    return user


def require_roles(*roles: RoleName):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return dependency


def get_current_organization(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    """Returns the organization the current request is scoped to.

    Prefers `user.organization_id` (the JWT claim, populated for staff users).
    Falls back to the single default organization for legacy users that
    pre-date the Phase 1 backfill. Raises 404 if `organization_id` is set
    but the row no longer exists.
    """

    if user.organization_id is not None:
        organization = db.scalars(
            select(Organization).where(Organization.id == user.organization_id)
        ).first()
        if organization is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User's organization no longer exists",
            )
        return organization

    organization = db.scalars(select(Organization).order_by(Organization.id)).first()
    if organization is None:
        organization = Organization(name="Cognivault Enterprise Demo", domain="cognivault.local")
        db.add(organization)
        db.commit()
        db.refresh(organization)
    return organization
