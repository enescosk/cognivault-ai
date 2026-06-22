import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Role, User


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).options(joinedload(User.role)).order_by(User.id)))


def list_roles(db: Session) -> list[Role]:
    return list(db.scalars(select(Role).order_by(Role.id)))


def user_profile_payload(user: User) -> dict:
    """
    Kullanıcı profilini döner.
    `phone` alanı: kayıtlıysa telefon numarası, yoksa None.
    Bu bilgi AI'a iletilir — randevu akışında "kayıtlı numarana onay göndereyim mi?" sorusu için kullanılır.
    """
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role.name.value,
        "locale": user.locale,
        "department": user.department,
        "title": user.title,
        # Randevu akışı telefon zekası için kritik alan
        "phone": user.phone,
    }


def normalize_phone(raw: str) -> str:
    """
    Telefon numarasını normalize eder: boşluk, tire, parantez temizler.
    Geçerli minimum uzunluk: 10 rakam (Türkiye: 05XX XXX XX XX).
    """
    cleaned = re.sub(r"[^\d+]", "", raw.strip())
    return cleaned


def update_user_phone(db: Session, user: User, new_phone: str) -> User:
    """
    Kullanıcının kayıtlı telefon numarasını günceller.

    Çağrı koşulları:
    - Kullanıcı randevu akışında yeni bir numara verdiğinde
    - Kullanıcı mevcut numarasını değiştirmek istediğinde

    Normalizasyon sonrası DB'ye yazılır; bir sonraki oturumda AI
    bu numarayı profilde görür ve tekrar sormaz.
    """
    normalized = normalize_phone(new_phone)
    user.phone = normalized
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_locale(db: Session, user: User, locale: str) -> User:
    if locale not in {"tr", "en"}:
        raise ValueError("Unsupported locale")
    user.locale = locale
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
