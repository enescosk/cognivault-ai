import pytest
from datetime import datetime, timezone, timedelta
from app.models import Clinic, ClinicPatient, ClinicConversation, ClinicMessage, ClinicMessageSender, ClinicChannel
from app.services.clinical_compliance_service import run_retention_cleanup


def test_retention_cleanup(db_session):
    # 1. Create a clinic
    clinic = Clinic(
        name="Test Retention Clinic",
        slug="retention-clinic",
        default_language="tr",
        settings_json={"branding": {}}
    )
    db_session.add(clinic)
    db_session.commit()
    db_session.refresh(clinic)

    now = datetime.now(timezone.utc)

    # 2. Create patients
    # Expired patient (data_expires_at passed)
    expired_patient = ClinicPatient(
        clinic_id=clinic.id,
        full_name="Mehmet Ak",
        phone="+905553332211",
        language="tr",
        source=ClinicChannel.WHATSAPP,
        data_expires_at=now - timedelta(days=1),
    )
    # Active patient (data_expires_at in future)
    active_patient = ClinicPatient(
        clinic_id=clinic.id,
        full_name="Fatma Ak",
        phone="+905553332212",
        language="tr",
        source=ClinicChannel.WHATSAPP,
        data_expires_at=now + timedelta(days=365),
    )
    db_session.add(expired_patient)
    db_session.add(active_patient)
    db_session.commit()

    # 3. Create conversation & messages
    conv = ClinicConversation(
        clinic_id=clinic.id,
        patient_id=expired_patient.id,
        channel=ClinicChannel.WHATSAPP,
        language="tr",
        data_expires_at=now - timedelta(days=1),
    )
    db_session.add(conv)
    db_session.commit()

    # Message older than 90 days
    old_msg = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conv.id,
        sender=ClinicMessageSender.PATIENT,
        content="Eski mesaj içeriği",
        language="tr",
        created_at=now - timedelta(days=91)
    )
    # Message newer than 90 days
    new_msg = ClinicMessage(
        clinic_id=clinic.id,
        conversation_id=conv.id,
        sender=ClinicMessageSender.PATIENT,
        content="Yeni mesaj içeriği",
        language="tr",
        created_at=now - timedelta(days=45)
    )
    db_session.add(old_msg)
    db_session.add(new_msg)
    db_session.commit()

    # 4. Run cleanup
    stats = run_retention_cleanup(db_session)
    assert stats["messages_erased"] == 1
    assert stats["patients_erased"] == 1
    assert stats["conversations_erased"] == 1

    # 5. Verify results
    db_session.refresh(expired_patient)
    db_session.refresh(active_patient)
    db_session.refresh(old_msg)
    db_session.refresh(new_msg)

    # Expired patient is anonymized
    assert expired_patient.full_name == "[SİLİNDİ]"
    assert expired_patient.phone.startswith("erased:")

    # Active patient is unchanged
    assert active_patient.full_name == "Fatma Ak"
    assert active_patient.phone == "+905553332212"

    # Old message is anonymized
    assert old_msg.content == "[İçerik KVKK gereği otomatik silindi]"

    # New message is unchanged
    assert new_msg.content == "Yeni mesaj içeriği"
