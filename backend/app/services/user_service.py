from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Role, User


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).options(joinedload(User.role)).order_by(User.id)))


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.id)))


def user_profile_payload(user: User) -> dict:
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.name.value,
        "locale": user.locale,
        "department": user.department,
        "title": user.title,
    }
