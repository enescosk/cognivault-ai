"""Kanal→klinik eşlemesi (ClinicChannelBinding + resolve_webhook_clinic).

Multi-tenant güvenlik değişmezi: bir webhook mesajı yalnızca aranan
numaranın/WABA kimliğinin bağlı olduğu kliniğe yazılabilir. Strict modda
eşleşmeyen adres reddedilir; demo modda default kliniğe düşer.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import (
    Clinic,
    ClinicChannel,
    ClinicChannelBinding,
    ClinicConversation,
)
from app.services.clinical_service import ensure_default_clinic, resolve_webhook_clinic


@pytest.fixture()
def strict_mode():
    s = get_settings()
    original = s.clinical_channel_binding_strict
    s.clinical_channel_binding_strict = True
    yield s
    s.clinical_channel_binding_strict = original


def _make_clinic(db, slug: str, name: str) -> Clinic:
    clinic = Clinic(name=name, slug=slug, settings_json={})
    db.add(clinic)
    db.commit()
    db.refresh(clinic)
    return clinic


def _bind(db, clinic: Clinic, channel: ClinicChannel, address: str) -> ClinicChannelBinding:
    binding = ClinicChannelBinding(clinic_id=clinic.id, channel=channel, address=address)
    db.add(binding)
    db.commit()
    return binding


# ─── Resolver birimi ─────────────────────────────────────────────────────────

def test_resolver_returns_bound_clinic(db_session):
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.PHONE, "+902165554433")

    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.PHONE, address="+90 216 555 44 33"
    )
    assert resolved is not None and resolved.id == clinic_b.id


def test_resolver_normalizes_whatsapp_prefix(db_session):
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.WHATSAPP, "+902165554433")

    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.WHATSAPP, address="whatsapp:+902165554433"
    )
    assert resolved is not None and resolved.id == clinic_b.id


def test_resolver_channel_is_part_of_key(db_session):
    """Aynı adres farklı kanalda başka kliniğe bağlanabilir; karışmamalı."""
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.WHATSAPP, "+902165554433")

    default = ensure_default_clinic(db_session)
    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.PHONE, address="+902165554433"
    )
    # PHONE kanalında binding yok → demo modda default kliniğe düşer.
    assert resolved is not None and resolved.id == default.id


def test_resolver_falls_back_to_default_when_unbound(db_session):
    default = ensure_default_clinic(db_session)
    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.PHONE, address="+900000000000"
    )
    assert resolved is not None and resolved.id == default.id


def test_resolver_strict_mode_rejects_unbound(db_session, strict_mode):
    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.PHONE, address="+900000000000"
    )
    assert resolved is None


def test_resolver_inactive_binding_ignored(db_session, strict_mode):
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    binding = _bind(db_session, clinic_b, ClinicChannel.PHONE, "+902165554433")
    binding.is_active = False
    db_session.add(binding)
    db_session.commit()

    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.PHONE, address="+902165554433"
    )
    assert resolved is None


def test_resolver_meta_phone_number_id_via_clinic_column(db_session):
    """Tarihsel Clinic.whatsapp_phone_number_id alanı da eşleşme kaynağı."""
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    clinic_b.whatsapp_phone_number_id = "108500123456789"
    db_session.add(clinic_b)
    db_session.commit()

    resolved = resolve_webhook_clinic(
        db_session, channel=ClinicChannel.WHATSAPP, address="108500123456789"
    )
    assert resolved is not None and resolved.id == clinic_b.id


# ─── Webhook yönlendirmesi (uçtan uca) ───────────────────────────────────────

def _post_twilio_whatsapp(client, *, to: str, from_: str, body: str):
    return client.post(
        "/api/webhooks/whatsapp",
        content=f"From={from_}&To={to}&Body={body}",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


def test_whatsapp_webhook_routes_to_bound_clinic(client, db_session):
    ensure_default_clinic(db_session)
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.WHATSAPP, "+902165554433")

    res = _post_twilio_whatsapp(
        client, to="whatsapp:%2B902165554433", from_="whatsapp:%2B905321112233",
        body="Dis agrim var randevu istiyorum",
    )
    assert res.status_code == 200

    conversation = db_session.scalars(
        select(ClinicConversation).order_by(ClinicConversation.id.desc())
    ).first()
    assert conversation is not None
    assert conversation.clinic_id == clinic_b.id


def test_whatsapp_webhook_unbound_falls_back_to_default(client, db_session):
    default = ensure_default_clinic(db_session)

    res = _post_twilio_whatsapp(
        client, to="whatsapp:%2B909999999999", from_="whatsapp:%2B905321112233",
        body="Randevu istiyorum",
    )
    assert res.status_code == 200
    conversation = db_session.scalars(
        select(ClinicConversation).order_by(ClinicConversation.id.desc())
    ).first()
    assert conversation is not None and conversation.clinic_id == default.id


def test_whatsapp_webhook_strict_rejects_unbound(client, db_session, strict_mode):
    ensure_default_clinic(db_session)
    before = len(db_session.scalars(select(ClinicConversation)).all())

    res = _post_twilio_whatsapp(
        client, to="whatsapp:%2B909999999999", from_="whatsapp:%2B905321112233",
        body="Randevu istiyorum",
    )
    assert res.status_code == 202
    after = len(db_session.scalars(select(ClinicConversation)).all())
    assert after == before  # hiçbir kliniğe veri yazılmadı


def test_voice_gather_routes_to_bound_clinic(client, db_session):
    ensure_default_clinic(db_session)
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.PHONE, "+902165554433")

    res = client.post(
        "/api/webhooks/voice/gather",
        content=(
            "SpeechResult=Dis+agrim+var+randevu+almak+istiyorum"
            "&From=%2B905321112233&To=%2B902165554433&CallSid=CAtest123"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200
    conversation = db_session.scalars(
        select(ClinicConversation).order_by(ClinicConversation.id.desc())
    ).first()
    assert conversation is not None and conversation.clinic_id == clinic_b.id


def test_voice_gather_strict_rejects_unbound_number(client, db_session, strict_mode):
    ensure_default_clinic(db_session)
    before = len(db_session.scalars(select(ClinicConversation)).all())

    res = client.post(
        "/api/webhooks/voice/gather",
        content=(
            "SpeechResult=Randevu+istiyorum"
            "&From=%2B905321112233&To=%2B909999999999&CallSid=CAtest456"
        ),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res.status_code == 200  # TwiML kibar kapanış döner
    assert "hizmet" in res.text
    assert "<Gather" not in res.text  # konuşma devam etmez
    after = len(db_session.scalars(select(ClinicConversation)).all())
    assert after == before


def test_meta_webhook_routes_by_phone_number_id(client, db_session):
    ensure_default_clinic(db_session)
    clinic_b = _make_clinic(db_session, "klinik-b", "Klinik B")
    _bind(db_session, clinic_b, ClinicChannel.WHATSAPP, "108500123456789")

    payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": "108500123456789"},
                    "contacts": [{"wa_id": "905321112233", "profile": {"name": "Test Hasta"}}],
                    "messages": [{
                        "id": "wamid.test1",
                        "from": "905321112233",
                        "text": {"body": "Dis agrim var randevu istiyorum"},
                    }],
                }
            }]
        }]
    }
    res = client.post("/api/webhooks/whatsapp", json=payload)
    assert res.status_code == 200
    conversation = db_session.scalars(
        select(ClinicConversation).order_by(ClinicConversation.id.desc())
    ).first()
    assert conversation is not None and conversation.clinic_id == clinic_b.id
