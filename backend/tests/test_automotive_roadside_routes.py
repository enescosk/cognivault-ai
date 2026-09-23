"""Yol yardımı uçları: Meta imzalı WhatsApp webhook, telefon, demo simülatörü."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AutomotiveCase

SECRET = 'test-only-meta-secret'
PHONE_ID = '1111222233334444'
CUSTOMER = '905321112233'
TEAM_01 = '+905300000001'


def auth(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def wa_live(monkeypatch):
    s = get_settings()
    for key, value in {
        'automotive_whatsapp_enabled': True,
        'automotive_meta_app_secret': SECRET,
        'automotive_whatsapp_phone_number_id': PHONE_ID,
        'automotive_meta_verify_token': 'verify-me',
        'automotive_inbound_owner_email': 'operator@test.com',
        'automotive_team_phones': json.dumps({'atlas-01': TEAM_01}),
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


def webhook_body(*messages, statuses=(), phone_id=PHONE_ID):
    return json.dumps({'object': 'whatsapp_business_account', 'entry': [{'id': 'WABA', 'changes': [{
        'field': 'messages', 'value': {
            'messaging_product': 'whatsapp', 'metadata': {'phone_number_id': phone_id},
            'contacts': [{'wa_id': CUSTOMER, 'profile': {'name': 'Ayşe'}}],
            'messages': list(messages), 'statuses': list(statuses)}}]}]}).encode()


def signed(client, body, secret=SECRET):
    signature = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post('/api/automotive/webhooks/whatsapp', content=body,
                       headers={'X-Hub-Signature-256': signature, 'Content-Type': 'application/json'})


def text(body, mid, sender=CUSTOMER):
    return {'from': sender, 'id': mid, 'type': 'text', 'text': {'body': body}}


# ─── WhatsApp webhook ────────────────────────────────────────────────────────


def test_webhook_off_by_default(client):
    assert signed(client, webhook_body(text('Çekici lazım', 'wamid.a'))).status_code == 503


def test_webhook_rejects_bad_signature(client, wa_live):
    assert signed(client, webhook_body(text('Çekici lazım', 'wamid.b')), secret='wrong').status_code == 401
    response = client.post('/api/automotive/webhooks/whatsapp', content=webhook_body(text('x', 'wamid.c')))
    assert response.status_code == 401


def test_webhook_verify_handshake(client, wa_live):
    ok = client.get('/api/automotive/webhooks/whatsapp',
                    params={'hub.mode': 'subscribe', 'hub.verify_token': 'verify-me', 'hub.challenge': '42'})
    assert ok.status_code == 200 and ok.text == '42'
    bad = client.get('/api/automotive/webhooks/whatsapp',
                     params={'hub.mode': 'subscribe', 'hub.verify_token': 'nope', 'hub.challenge': '42'})
    assert bad.status_code == 403


def test_signed_customer_message_opens_case(client, db_session, wa_live):
    response = signed(client, webhook_body(text('Yolda kaldım, çekici lazım', 'wamid.d')))
    assert response.status_code == 200 and response.json()['received'] == 1
    row = db_session.scalar(select(AutomotiveCase).where(AutomotiveCase.request_key == 'wa:wamid.d'))
    assert row.data['service'] == 'tow' and row.data['contact'] == '+' + CUSTOMER
    # Meta aynı partiyi tekrar gönderirse ikinci iş açılmaz.
    signed(client, webhook_body(text('Yolda kaldım, çekici lazım', 'wamid.d')))
    assert len(db_session.scalars(select(AutomotiveCase)).all()) == 1


def test_other_business_number_is_ignored(client, db_session, wa_live):
    response = signed(client, webhook_body(text('Çekici lazım', 'wamid.e'), phone_id='9999'))
    assert response.json()['received'] == 0
    assert db_session.scalars(select(AutomotiveCase)).all() == []


def test_unsupported_message_asks_to_type(client, db_session, wa_live):
    signed(client, webhook_body({'from': CUSTOMER, 'id': 'wamid.f', 'type': 'audio', 'audio': {'id': 'x'}}))
    row = db_session.scalar(select(AutomotiveCase))
    assert any('sesli mesaj' in m['text'].lower() for m in row.data['messages'])


def test_webhook_without_owner_config_fails_closed(client, wa_live, monkeypatch):
    monkeypatch.setattr(get_settings(), 'automotive_inbound_owner_email', '')
    assert signed(client, webhook_body(text('Çekici lazım', 'wamid.g'))).status_code == 503


# ─── Simülatör ───────────────────────────────────────────────────────────────


def sim(client, token, path, **body):
    return client.post(f'/api/automotive/operations/simulate/{path}', json=body, headers=auth(token))


def test_simulator_runs_full_tow_flow(client, operator_token):
    phone = '+905321112233'
    r = sim(client, operator_token, 'customer', phone=phone, text='Çekici lazım').json()
    case_id = r['case']['id']
    sim(client, operator_token, 'customer', phone=phone, kind='reply', reply_id='c:safe:ok')
    sim(client, operator_token, 'customer', phone=phone, kind='location', latitude=41.01, longitude=29.07)
    sim(client, operator_token, 'customer', phone=phone, text='34 ABC 123 Fiat Egea')
    sim(client, operator_token, 'customer', phone=phone, kind='reply', reply_id='c:dest:service')
    r = sim(client, operator_token, 'customer', phone=phone, kind='reply', reply_id='c:share:yes').json()
    assert r['case']['status'] == 'offered'
    r = sim(client, operator_token, 'team', team_id='atlas-01', reply_id=f't:accept15:{case_id}').json()
    assert r['case']['status'] == 'accepted'

    messages = client.get(f'/api/automotive/operations/cases/{case_id}/messages', headers=auth(operator_token)).json()
    assert {m['delivery_status'] for m in messages if m['direction'] == 'out'} == {'demo_only'}
    assert any(m['audience'] == 'team:atlas-01' and m['purpose'] == 'team_offer' for m in messages)


def test_simulator_call_and_expire(client, operator_token):
    r = sim(client, operator_token, 'call', phone='+905321112233', speech='Lastiğim patladı').json()
    assert r['transfer'] and r['case']['service'] == 'tire'
    assert sim(client, operator_token, 'expire-offers').json() == {'expired': 0}


def test_simulator_closed_when_live(client, operator_token, wa_live):
    assert sim(client, operator_token, 'customer', phone='+905321112233', text='x').status_code == 409
    assert sim(client, operator_token, 'call', speech='x').status_code == 409


def test_simulator_requires_staff(client, customer_token):
    assert sim(client, customer_token, 'customer', phone='+905321112233', text='x').status_code == 403


def test_messages_are_owner_scoped(client, operator_token, admin_token):
    r = sim(client, operator_token, 'customer', phone='+905321112233', text='Çekici lazım').json()
    other = client.get(f"/api/automotive/operations/cases/{r['case']['id']}/messages", headers=auth(admin_token))
    assert other.status_code == 404


def test_catalog_reports_modes(client, operator_token, wa_live):
    catalog = client.get('/api/automotive/operations/catalog', headers=auth(operator_token)).json()
    assert catalog['whatsapp_connected'] is True and catalog['simulator_enabled'] is False
    assert catalog['offer_timeout_minutes'] == 5


# ─── Telefon ─────────────────────────────────────────────────────────────────


@pytest.fixture
def phone_live(monkeypatch):
    s = get_settings()
    for key, value in {
        'automotive_voice_enabled': True,
        'automotive_inbound_number': '+905550000001',
        'automotive_dispatch_number': '+905550000002',
        'automotive_webhook_base_url': 'https://auto.example.test',
        'twilio_account_sid': 'AC-example',
        'twilio_auth_token': 'test-only-secret',
        'automotive_inbound_owner_email': 'operator@test.com',
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


def signed_call(client, settings, path, fields):
    url = settings.automotive_webhook_base_url + path
    canonical = url + ''.join(k + fields[k] for k in sorted(fields))
    signature = base64.b64encode(hmac.new(settings.twilio_auth_token.encode(), canonical.encode(),
                                          hashlib.sha1).digest()).decode()
    return client.post(path, data=fields, headers={'X-Twilio-Signature': signature})


def call_fields(settings, **extra):
    return {'To': settings.automotive_inbound_number, 'AccountSid': settings.twilio_account_sid,
            'CallSid': 'CAlive1', 'From': '+905321112233'} | extra


def test_signed_call_opens_case_and_transfers(client, db_session, phone_live):
    response = signed_call(client, phone_live, '/api/automotive/webhooks/voice/gather',
                           call_fields(phone_live, SpeechResult='Aracım çalışmıyor çekici lazım'))
    assert response.status_code == 200
    assert '<Number>+905550000002</Number>' in response.text
    row = db_session.scalar(select(AutomotiveCase).where(AutomotiveCase.request_key == 'call:CAlive1'))
    assert row.data['service'] == 'tow' and row.data['channel'] == 'phone'


def test_unclear_call_is_asked_again_with_next_attempt(client, phone_live):
    response = signed_call(client, phone_live, '/api/automotive/webhooks/voice/gather',
                           call_fields(phone_live, SpeechResult='Şey merhaba'))
    assert 'attempt=2' in response.text and 'Aracınızda ne oldu' in response.text
    assert '<Number>+905550000002</Number>' in response.text  # sessizlikte de ekibe düşer


def test_call_never_drops_without_owner(client, db_session, phone_live, monkeypatch):
    monkeypatch.setattr(phone_live, 'automotive_inbound_owner_email', '')
    response = signed_call(client, phone_live, '/api/automotive/webhooks/voice/gather',
                           call_fields(phone_live, SpeechResult='Çekici lazım'))
    assert response.status_code == 200
    assert '<Number>+905550000002</Number>' in response.text
    assert db_session.scalars(select(AutomotiveCase)).all() == []
