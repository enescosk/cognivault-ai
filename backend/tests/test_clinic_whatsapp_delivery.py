"""Klinik WhatsApp cevaplarının hastaya GERÇEKTEN gönderilmesi.

Önceki durum: cevap üretiliyor ama yalnız `"delivery": "simulated"` diye
kaydediliyordu — hasta WhatsApp'ta hiçbir cevap almıyordu, KVKK aydınlatması
da ona ulaşmıyordu.

Korunan değişmezler:
- Gönderim ayarı kapalıyken hiçbir numaraya mesaj gitmez (demo_only).
- Operatör simülasyonu gerçek gönderim tetiklemez.
- Hasta yeniden yazınca eski "simulated" cevaplar toptan gönderilmez.
- Cevap, mesajın geldiği işletme numarasından gider.
- 24 saat penceresi kapalıyken serbest mesaj gitmez; konuşma insana düşer.
- Teslim edilemeyen mesaj sessiz kalmaz; konuşma insana düşer.
- Durum yalnız ileri gider (okundu, sonra gelen "iletildi" ile geri alınmaz).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.channels import whatsapp_meta as meta
from app.channels import whatsapp_twilio as twilio
from app.core.config import get_settings
from app.models import (
    ClinicConversation,
    ClinicConversationStatus,
    ClinicMessage,
    ClinicMessageSender,
    OutboxEvent,
    ShadowReview,
)
from app.services import clinic_whatsapp

BUSINESS = 'whatsapp:+902120000000'
META_NUMBER_ID = '5550001112223334'


@pytest.fixture
def live(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, 'clinic_whatsapp_send_enabled', True)
    monkeypatch.setattr(s, 'twilio_account_sid', 'AC-test')
    monkeypatch.setattr(s, 'twilio_auth_token', 'test-only')
    monkeypatch.setattr(s, 'meta_access_token', 'meta-test-token')
    return s


def twilio_in(client, body, *, phone='+905551112200', sid='SM1', to=BUSINESS):
    return client.post('/api/webhooks/whatsapp', data={'From': f'whatsapp:{phone}', 'To': to, 'Body': body,
                       'MessageSid': sid}, headers={'Content-Type': 'application/x-www-form-urlencoded'}).json()


def meta_in(client, body, *, wa_id='905551112299', mid='wamid.IN1', statuses=()):
    payload = {'object': 'whatsapp_business_account', 'entry': [{'id': 'WABA', 'changes': [{'field': 'messages', 'value': {
        'messaging_product': 'whatsapp',
        'metadata': {'display_phone_number': '902120000000', 'phone_number_id': META_NUMBER_ID},
        'contacts': [{'wa_id': wa_id, 'profile': {'name': 'Meta Hasta'}}],
        'messages': [{'from': wa_id, 'id': mid, 'type': 'text', 'text': {'body': body}}] if body else [],
        'statuses': list(statuses)}}]}]}
    return client.post('/api/webhooks/whatsapp', content=json.dumps(payload),
                       headers={'Content-Type': 'application/json'}).json()


def outbound(db, conversation_id):
    return db.scalars(select(ClinicMessage).where(
        ClinicMessage.conversation_id == conversation_id,
        ClinicMessage.sender != ClinicMessageSender.PATIENT,
    ).order_by(ClinicMessage.id)).all()


def delivery(message):
    return (message.metadata_json or {}).get('delivery')


class _Same:
    """Handler kendi oturumunu `with` ile açar; testte aynı oturumu kapatmadan ver."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False


def run_outbox(db):
    handler = clinic_whatsapp.make_delivery_handler(lambda: _Same(db))
    for event in db.scalars(select(OutboxEvent).where(OutboxEvent.event_type == clinic_whatsapp.OUTBOX_EVENT)).all():
        handler(event)


# ─── Varsayılan: hiçbir şey gitmez ───────────────────────────────────────────


def test_default_sends_nothing_but_marks_demo(client, db_session):
    data = twilio_in(client, 'Randevu almak istiyorum')
    messages = outbound(db_session, data['conversation_id'])
    assert [delivery(m) for m in messages] == ['demo_only', 'demo_only']  # KVKK + cevap
    assert db_session.scalars(select(OutboxEvent)).all() == []


def test_operator_simulation_never_triggers_delivery(client, db_session, operator_token, live):
    response = client.post('/api/clinical/simulate-whatsapp', json={'from_phone': '+905551112277',
                           'body': 'Randevu almak istiyorum'}, headers={'Authorization': f'Bearer {operator_token}'})
    assert response.status_code == 200
    conversation_id = response.json()['conversation_id']
    assert {delivery(m) for m in outbound(db_session, conversation_id)} == {'simulated'}
    assert db_session.scalars(select(OutboxEvent)).all() == []


# ─── Canlı: Twilio ───────────────────────────────────────────────────────────


def test_twilio_reply_is_queued_sent_and_tracked(client, db_session, live, monkeypatch):
    data = twilio_in(client, 'Randevu almak istiyorum')
    messages = outbound(db_session, data['conversation_id'])
    assert [delivery(m) for m in messages] == ['queued', 'queued']
    assert (messages[0].metadata_json or {}).get('kvkk_notice') is True  # aydınlatma önce gider

    sent = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return f'SMOUT{len(sent)}'
    monkeypatch.setattr(twilio, 'send_text', fake_send)
    run_outbox(db_session)
    assert [s['from_'] for s in sent] == [BUSINESS, BUSINESS]  # geldiği numaradan
    assert sent[0]['to'] == '+905551112200'
    for m in messages:
        db_session.refresh(m)
    assert [delivery(m) for m in messages] == ['accepted', 'accepted']  # kabul ≠ teslim
    assert messages[1].external_message_id == 'SMOUT2'

    status = lambda st: client.post('/api/webhooks/whatsapp/status', data={'MessageSid': 'SMOUT2', 'MessageStatus': st},
                                    headers={'Content-Type': 'application/x-www-form-urlencoded'})
    assert status('read').status_code == 200
    status('delivered')  # sıra dışı geldi — geri alınmaz
    db_session.refresh(messages[1])
    assert delivery(messages[1]) == 'read'


def test_twilio_undelivered_hands_conversation_to_human(client, db_session, live, monkeypatch):
    data = twilio_in(client, 'Randevu almak istiyorum', sid='SM2')
    monkeypatch.setattr(twilio, 'send_text', lambda **kw: 'SMOUTX')
    run_outbox(db_session)
    client.post('/api/webhooks/whatsapp/status', data={'MessageSid': 'SMOUTX', 'MessageStatus': 'undelivered',
                'ErrorCode': '63016'}, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    conversation = db_session.get(ClinicConversation, data['conversation_id'])
    db_session.refresh(conversation)
    assert conversation.status == ClinicConversationStatus.WAITING_HUMAN
    assert 'iletilemedi' in conversation.metadata_json['whatsapp_delivery_problem']


def test_permanent_send_error_is_not_retried_and_escalates(client, db_session, live, monkeypatch):
    data = twilio_in(client, 'Randevu almak istiyorum', sid='SM3')

    def reject(**kw):
        raise meta.PermanentSendError('400 invalid To')
    monkeypatch.setattr(twilio, 'send_text', reject)
    run_outbox(db_session)
    messages = outbound(db_session, data['conversation_id'])
    for m in messages:
        db_session.refresh(m)
    assert {delivery(m) for m in messages} == {'failed'}
    conversation = db_session.get(ClinicConversation, data['conversation_id'])
    db_session.refresh(conversation)
    assert conversation.status == ClinicConversationStatus.WAITING_HUMAN


# ─── Canlı: Meta ─────────────────────────────────────────────────────────────


def test_meta_reply_goes_from_receiving_number(client, db_session, live, monkeypatch):
    results = meta_in(client, 'Randevu almak istiyorum')
    conversation_id = results[0]['conversation_id']
    sent = []
    monkeypatch.setattr(meta, 'send', lambda message, **kw: sent.append((message, kw)) or f'wamid.OUT{len(sent)}')
    run_outbox(db_session)
    assert {kw['phone_number_id'] for _, kw in sent} == {META_NUMBER_ID}
    assert sent[0][0]['to'] == '905551112299'  # Meta "+"sız numara verdi; biz de öyle gönderdik
    assert sent[-1][0]['type'] == 'text'

    meta_in(client, '', statuses=[{'id': 'wamid.OUT2', 'status': 'delivered'}])
    reply = outbound(db_session, conversation_id)[-1]
    db_session.refresh(reply)
    assert delivery(reply) == 'delivered'


# ─── Hekim incelemesi ────────────────────────────────────────────────────────


def test_escalated_message_gets_acknowledged_not_silence(client, db_session, live):
    data = twilio_in(client, 'Disim cok agriyor', sid='SM4')
    assert data['action'] == 'shadow_review'
    ack = outbound(db_session, data['conversation_id'])[-1]
    assert (ack.metadata_json or {}).get('shadow_ack') is True
    assert 'hekimimize ilettim' in ack.content and delivery(ack) == 'queued'


def test_emergency_acknowledgement_says_112(client, db_session, live):
    data = twilio_in(client, 'Nefes alamiyorum gogsum sikisiyor', sid='SM5')
    ack = outbound(db_session, data['conversation_id'])[-1]
    assert '112' in ack.content


def test_doctor_approved_reply_reaches_patient(client, db_session, live, operator_token):
    data = twilio_in(client, 'Disim cok agriyor', sid='SM6')
    review = db_session.scalar(select(ShadowReview).where(ShadowReview.conversation_id == data['conversation_id']))
    response = client.patch(f'/api/clinical/shadow-reviews/{review.id}',
                            json={'status': 'edited', 'final_reply': 'Yarın 10:00 için yer açtık, uygun mu?'},
                            headers={'Authorization': f'Bearer {operator_token}'})
    assert response.status_code == 200
    reply = outbound(db_session, data['conversation_id'])[-1]
    assert reply.sender == ClinicMessageSender.OPERATOR
    assert reply.content.startswith('Yarın 10:00') and delivery(reply) == 'queued'


def test_late_approval_outside_24h_is_blocked_and_escalated(client, db_session, live, operator_token):
    data = twilio_in(client, 'Disim cok agriyor', sid='SM7')
    patient_message = db_session.scalar(select(ClinicMessage).where(
        ClinicMessage.conversation_id == data['conversation_id'], ClinicMessage.sender == ClinicMessageSender.PATIENT))
    patient_message.created_at = datetime.now(timezone.utc) - timedelta(hours=25)
    db_session.commit()
    review = db_session.scalar(select(ShadowReview).where(ShadowReview.conversation_id == data['conversation_id']))
    client.patch(f'/api/clinical/shadow-reviews/{review.id}', json={'status': 'approved'},
                 headers={'Authorization': f'Bearer {operator_token}'})
    reply = outbound(db_session, data['conversation_id'])[-1]
    assert delivery(reply) == 'blocked_no_template'
    conversation = db_session.get(ClinicConversation, data['conversation_id'])
    db_session.refresh(conversation)
    assert conversation.status == ClinicConversationStatus.WAITING_HUMAN


# ─── Geçmiş kayıtlar ─────────────────────────────────────────────────────────


def test_old_simulated_replies_are_never_bulk_sent(client, db_session, live):
    first = twilio_in(client, 'Randevu almak istiyorum', sid='SM8')
    for m in outbound(db_session, first['conversation_id']):
        m.metadata_json = {**(m.metadata_json or {}), 'delivery': 'simulated'}  # geçmişten kalma
    db_session.commit()
    second = twilio_in(client, 'Randevu almak istiyorum yarin', sid='SM9')
    assert second['conversation_id'] == first['conversation_id']
    deliveries = [delivery(m) for m in outbound(db_session, first['conversation_id'])]
    assert deliveries.count('simulated') == 2  # eskiler olduğu gibi
    assert deliveries[-1] == 'queued'          # yalnız yeni cevap


def test_live_without_business_number_fails_loudly(client, db_session, live):
    data = twilio_in(client, 'Randevu almak istiyorum', sid='SM10', to='')
    assert {delivery(m) for m in outbound(db_session, data['conversation_id'])} == {'failed'}
