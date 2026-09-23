from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.automotive import operations as ops
from app.automotive.channels import location_payload, parse_meta_location, transfer_twiml
from app.models import AutomotiveCase, User


@pytest.fixture
def staff_user(db_session):
    return db_session.scalar(select(User).where(User.email == 'operator@test.com'))


def create(db, user, service='tow', key=None):
    return ops.create_case(db, user, ops.CreateCase(service=service, request_key=key or str(uuid4())))


def action(db, user, case, kind, **kwargs):
    return ops.act(db, user, case['id'], ops.Action(version=case['version'], event_key=str(uuid4()), kind=kind, **kwargs))


def ready_case(db, user, service='tow'):
    case = create(db, user, service)
    case = action(db, user, case, 'details', vehicle='Örnek araç', destination='Atlas', safe=True)
    case = action(db, user, case, 'location', location=ops.Location(latitude=41.01, longitude=29.07, source='whatsapp'))
    return action(db, user, case, 'share', permission=True)


def test_end_to_end_persisted_tow(db_session, staff_user):
    c = ready_case(db_session, staff_user)
    assert c['status'] == 'ready'
    c = action(db_session, staff_user, c, 'offer', team_id='atlas-01')
    assert c['status'] == 'offered'
    assert c['handoff']['delivery_status'] == 'demo_only'
    assert '41.01,29.07' in c['handoff']['map_url']
    c = action(db_session, staff_user, c, 'accept', eta_minutes=25)
    for step in ['en_route', 'arrived', 'transport', 'complete']:
        c = action(db_session, staff_user, c, step)
    assert c['status'] == 'completed'
    db_session.expire_all()
    row = ops.fetch(db_session, staff_user, c['id'])
    assert row.team_slot is None
    assert row.version == c['version']
    assert row.data['status'] == 'completed'
    assert c['delivery_enabled'] is False


@pytest.mark.parametrize('service,team', [('battery', 'atlas-02'), ('tire', 'atlas-02'), ('fuel', 'atlas-02'), ('ev', 'atlas-01'), ('accident', 'atlas-01')])
def test_mobile_capabilities(db_session, staff_user, service, team):
    c = ready_case(db_session, staff_user, service)
    assert team in [t['id'] for t in ops.candidates(c)]


@pytest.mark.parametrize('service', [s['id'] for s in ops.CATALOG if not s['mobile']])
def test_all_workshop_requests_registered_without_booking_claim(db_session, staff_user, service):
    c = create(db_session, staff_user, service)
    c = action(db_session, staff_user, c, 'details', vehicle='Demo araç')
    assert c['status'] == 'service_requested'
    assert c['assigned_team'] is None


def test_no_locksmith_no_made_up_team(db_session, staff_user):
    c = ready_case(db_session, staff_user, 'locked')
    assert not ops.candidates(c)
    with pytest.raises(HTTPException):
        action(db_session, staff_user, c, 'offer', team_id='atlas-01')


@pytest.mark.parametrize('step', ['offer', 'accept', 'en_route', 'arrived', 'transport', 'complete'])
def test_cannot_skip_prerequisites(db_session, staff_user, step):
    c = create(db_session, staff_user)
    with pytest.raises(HTTPException) as exc:
        action(db_session, staff_user, c, step, team_id='atlas-01', eta_minutes=20)
    assert exc.value.status_code == 409
    assert ops.fetch(db_session, staff_user, c['id']).version == 1


def test_location_without_permission_cannot_dispatch(db_session, staff_user):
    c = ready_case(db_session, staff_user)
    c = action(db_session, staff_user, c, 'share', permission=False)
    with pytest.raises(HTTPException):
        action(db_session, staff_user, c, 'offer', team_id='atlas-01')


def test_changed_location_resets_permission(db_session, staff_user):
    c = ready_case(db_session, staff_user)
    c = action(db_session, staff_user, c, 'location', location=ops.Location(latitude=41.02, longitude=29.08))
    assert not c['share_permission']


def test_unsafe_caller_never_dispatched(db_session, staff_user):
    c = create(db_session, staff_user)
    c = action(db_session, staff_user, c, 'details', vehicle='Demo', safe=False)
    assert c['status'] == 'emergency'
    with pytest.raises(HTTPException):
        action(db_session, staff_user, c, 'location', location=ops.Location(latitude=41, longitude=29))


def test_same_create_key_deduplicates_and_mismatch_conflicts(db_session, staff_user):
    key = str(uuid4())
    c = create(db_session, staff_user, key=key)
    assert create(db_session, staff_user, key=key)['id'] == c['id']
    with pytest.raises(HTTPException):
        create(db_session, staff_user, service='battery', key=key)


def test_action_retry_stale_version_and_key_reuse(db_session, staff_user):
    c = create(db_session, staff_user)
    body = ops.Action(event_key=str(uuid4()), version=1, kind='message', text='Fiyat nedir?')
    result = ops.act(db_session, staff_user, c['id'], body)
    assert ops.act(db_session, staff_user, c['id'], body)['version'] == result['version']
    with pytest.raises(HTTPException):
        ops.act(db_session, staff_user, c['id'], body.model_copy(update={'text': 'Başka mesaj'}))
    with pytest.raises(HTTPException):
        action(db_session, staff_user, c, 'human')


def test_team_double_booking_blocked_and_release(db_session, staff_user):
    c1 = ready_case(db_session, staff_user)
    c2 = ready_case(db_session, staff_user)
    c1 = action(db_session, staff_user, c1, 'offer', team_id='atlas-01')
    with pytest.raises(HTTPException) as exc:
        action(db_session, staff_user, c2, 'offer', team_id='atlas-01')
    assert exc.value.status_code == 409
    action(db_session, staff_user, c1, 'decline')
    assert action(db_session, staff_user, c2, 'offer', team_id='atlas-01')['status'] == 'offered'


def test_emergency_and_cancellation_do_not_silently_release_accepted_team(db_session, staff_user):
    c = ready_case(db_session, staff_user)
    c = action(db_session, staff_user, c, 'offer', team_id='atlas-01')
    c = action(db_session, staff_user, c, 'accept', eta_minutes=20)
    c = action(db_session, staff_user, c, 'message', text='Araç yanıyor')
    assert c['status'] == 'emergency'
    assert ops.fetch(db_session, staff_user, c['id']).team_slot == 'atlas-01'
    c = action(db_session, staff_user, c, 'cancel')
    assert c['status'] == 'human'
    c = action(db_session, staff_user, c, 'cancel_confirmed')
    assert c['status'] == 'cancelled'
    assert ops.fetch(db_session, staff_user, c['id']).team_slot is None


def test_scope_is_owner_and_organization(db_session, staff_user):
    c = create(db_session, staff_user)
    another = db_session.scalar(select(User).where(User.email == 'admin@test.com'))
    with pytest.raises(HTTPException) as exc:
        ops.fetch(db_session, another, c['id'])
    assert exc.value.status_code == 404


def test_outside_coverage_and_busy_team(db_session, staff_user):
    c = ready_case(db_session, staff_user)
    assert 'atlas-03' not in [t['id'] for t in ops.candidates(c)]
    c = action(db_session, staff_user, c, 'location', location=ops.Location(latitude=0, longitude=0))
    assert not ops.candidates(c)


@pytest.mark.parametrize('latitude,longitude', [(91, 29), (41, 181), (float('nan'), 29), (41, float('inf'))])
def test_bad_location_rejected(latitude, longitude):
    with pytest.raises(ValidationError):
        ops.Location(latitude=latitude, longitude=longitude)


def test_meta_location_adapter_no_external_request():
    parsed = parse_meta_location({'id': 'wamid.example', 'type': 'location', 'location': {'latitude': 41.01, 'longitude': 29.07, 'name': 'Örnek konum'}})
    assert parsed['location']['source'] == 'whatsapp'
    out = location_payload(team_phone='+905550000000', location=ops.Location(**parsed['location']))
    assert out['type'] == 'location'
    assert out['to'] == '905550000000'
    assert out['location']['latitude'] == 41.01
    with pytest.raises(ValueError):
        parse_meta_location({'type': 'text'})


def test_twiml_number_validation_and_fallback():
    text = transfer_twiml('+905550000000')
    assert 'answerOnBridge="true"' in text and '<Number>+905550000000</Number>' in text
    assert '<Dial' not in transfer_twiml()
    with pytest.raises(ValueError):
        transfer_twiml('sip:untrusted.example')


def test_api_authorization_persistence_and_location(client, operator_token, admin_token, customer_token):
    h = {'Authorization': f'Bearer {operator_token}'}
    base = '/api/automotive/operations'
    assert client.get(f'{base}/cases').status_code == 401
    assert client.get(f'{base}/cases', headers={'Authorization': f'Bearer {customer_token}'}).status_code == 403
    c = client.post(f'{base}/cases', headers=h, json={'request_key': str(uuid4()), 'service': 'tow'}).json()
    assert client.get(f"{base}/cases/{c['id']}", headers={'Authorization': f'Bearer {admin_token}'}).status_code == 404
    response = client.post(f"{base}/cases/{c['id']}/whatsapp-location", headers=h,
                           json={'event_key': str(uuid4()), 'version': 1, 'latitude': 41.01, 'longitude': 29.07})
    assert response.status_code == 200
    assert response.json()['location']['source'] == 'whatsapp'
    rows = client.get(f'{base}/cases', headers=h).json()
    assert rows[0]['id'] == c['id'] and rows[0]['version'] == 2
    assert 'events' not in rows[0] and 'create_hash' not in rows[0]


@pytest.fixture
def phone_settings(monkeypatch):
    from app.core.config import get_settings
    s = get_settings()
    for key, value in {
        'automotive_voice_enabled': True,
        'automotive_inbound_number': '+905550000001',
        'automotive_dispatch_number': '+905550000002',
        'automotive_webhook_base_url': 'https://auto.example.test',
        'twilio_account_sid': 'AC-example',
        'twilio_auth_token': 'test-only-secret',
    }.items():
        monkeypatch.setattr(s, key, value)
    return s


def signed_call(client, settings, path, fields):
    import hmac, hashlib, base64
    url = settings.automotive_webhook_base_url + path
    canonical = url + ''.join(k + fields[k] for k in sorted(fields))
    signature = base64.b64encode(hmac.new(settings.twilio_auth_token.encode(), canonical.encode(), hashlib.sha1).digest()).decode()
    return client.post(path, data=fields, headers={'X-Twilio-Signature': signature})


def test_phone_routes_off_by_default(client):
    assert client.post('/api/automotive/webhooks/voice/incoming').status_code == 503


def test_phone_signature_always_required(client, phone_settings):
    assert client.post('/api/automotive/webhooks/voice/incoming', data={'To': phone_settings.automotive_inbound_number}).status_code == 401


@pytest.mark.parametrize('route,fields,expected', [
    ('incoming', {}, 'Nasıl yardımcı'),
    ('gather', {'SpeechResult': 'çekici istiyorum'}, '<Number>+905550000002</Number>'),
    ('transfer-status', {'DialCallStatus': 'busy'}, 'Henüz çekici sevk edilmedi'),
    ('transfer-status', {'DialCallStatus': 'completed'}, 'görüşmeniz sona erdi'),
])
def test_signed_phone_flow(client, phone_settings, route, fields, expected):
    payload = {'To': phone_settings.automotive_inbound_number, 'AccountSid': phone_settings.twilio_account_sid} | fields
    response = signed_call(client, phone_settings, '/api/automotive/webhooks/voice/' + route, payload)
    assert response.status_code == 200
    assert expected.lower() in response.text.lower()
    assert 'application/xml' in response.headers['content-type']


def test_signed_wrong_tenant_number_rejected(client, phone_settings):
    response = signed_call(client, phone_settings, '/api/automotive/webhooks/voice/incoming',
                           {'To': '+905550000099', 'AccountSid': phone_settings.twilio_account_sid})
    assert response.status_code == 403


def test_phone_loop_refused(client, phone_settings, monkeypatch):
    monkeypatch.setattr(phone_settings, 'automotive_dispatch_number', phone_settings.automotive_inbound_number)
    assert client.post('/api/automotive/webhooks/voice/incoming').status_code == 503
