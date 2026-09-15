"""Patient consent is scoped to a clinic and conversation; latest decision wins."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConsentRecord, ConsentType


def has_active_consent(
    db: Session, *, clinic_id: int, patient_id: int,
    conversation_id: int, consent_type: ConsentType,
) -> bool:
    latest = db.scalars(select(ConsentRecord).where(
        ConsentRecord.clinic_id == clinic_id,
        ConsentRecord.patient_id == patient_id,
        ConsentRecord.conversation_id == conversation_id,
        ConsentRecord.consent_type == consent_type,
    ).order_by(ConsentRecord.granted_at.desc(), ConsentRecord.id.desc())).first()
    return bool(latest and latest.granted and latest.withdrawn_at is None)
