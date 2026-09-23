from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.automotive.pilot import PreviewRequest, RehearsalRequest, VehicleRecord, demo_data, evaluate, preview, rehearse

TODAY = date(2026, 9, 23)


def record(**changes):
    data = demo_data(TODAY).records[0].model_dump() | changes
    return VehicleRecord.model_validate(data)


def test_demo_summary_and_no_side_effect_claims():
    result = preview(demo_data(TODAY))
    assert result['summary'] == {'ready': 2, 'review': 1, 'blocked': 4, 'not_due': 1}
    assert result['delivery_enabled'] is result['booking_enabled'] is False


@pytest.mark.parametrize('changes', [
    {'do_not_contact': True}, {'ownership_verified': False}, {'permitted_channels': []},
    {'consent_ref': None}, {'consent_checked_on': TODAY - timedelta(days=1)},
    {'consent_checked_on': TODAY + timedelta(days=1)}, {'open_booking': True},
    {'last_contact_on': TODAY - timedelta(days=29)},
])
def test_blocks_contact_even_when_due(changes):
    decision = evaluate(record(**changes), TODAY, 'sms')
    assert decision.status == 'blocked'
    assert decision.draft is None


def test_channel_specific_permission():
    assert evaluate(record(), TODAY, 'whatsapp').status == 'blocked'
    assert evaluate(record(), TODAY, 'phone').status == 'ready'


@pytest.mark.parametrize('changes', [
    {'synced_on': TODAY - timedelta(days=8)}, {'synced_on': TODAY + timedelta(days=1)},
    {'last_contact_on': TODAY + timedelta(days=1)},
    {'odometer_km': 50000, 'odometer_on': TODAY + timedelta(days=1)},
    {'next_service_on': None, 'next_service_km': None},
    {'next_service_on': None, 'next_service_km': 60000},
    {'next_service_on': None, 'next_service_km': 60000, 'odometer_km': 70000,
     'odometer_on': TODAY - timedelta(days=31)},
])
def test_incomplete_or_inconsistent_data_never_invents_due_date(changes):
    decision = evaluate(record(**changes), TODAY, 'sms')
    assert decision.status == 'review'
    assert decision.draft is None


@pytest.mark.parametrize('delta,status', [(30, 'ready'), (31, 'not_due'), (0, 'ready'), (-1, 'ready')])
def test_date_boundary(delta, status):
    assert evaluate(record(next_service_on=TODAY + timedelta(days=delta)), TODAY, 'sms').status == status


def test_mileage_boundary_and_no_extrapolation():
    data = dict(next_service_on=None, next_service_km=60000, odometer_on=TODAY)
    assert evaluate(record(**data, odometer_km=59999), TODAY, 'sms').status == 'not_due'
    decision = evaluate(record(**data, odometer_km=60000), TODAY, 'sms')
    assert decision.status == 'ready'
    assert '60,000' in decision.draft


def test_valid_date_still_works_without_mileage():
    decision = evaluate(record(next_service_km=60000), TODAY, 'sms')
    assert decision.status == 'ready'
    assert '05.10.2026' in decision.draft
    assert 'km' not in decision.draft


def test_cooldown_boundary():
    assert evaluate(record(last_contact_on=TODAY - timedelta(days=30)), TODAY, 'sms').status == 'ready'


@pytest.mark.parametrize('changes', [{'odometer_km': -1}, {'odometer_km': 20},
                                     {'odometer_on': TODAY}, {'vehicle_id': ''}, {'unknown_field': True}])
def test_invalid_source_fields_rejected(changes):
    with pytest.raises(ValidationError):
        record(**changes)


def test_duplicate_source_records_rejected():
    with pytest.raises(ValidationError):
        PreviewRequest(as_of=TODAY, records=[record(), record()])


@pytest.mark.parametrize('outcome', ['interested', 'already_serviced', 'opt_out', 'wrong_person', 'price', 'urgent', 'human'])
def test_rehearsal_never_claims_persistence_or_booking(outcome):
    result = rehearse(RehearsalRequest(vehicle_id='demo-01', outcome=outcome))
    assert not result['persisted']
    assert not result['booking_confirmed']
    assert result['required_steps']


def test_blocked_customer_cannot_enter_outbound_booking_rehearsal():
    result = rehearse(RehearsalRequest(vehicle_id='demo-03', outcome='interested'))
    assert result['stage'] == 'blocked'


def test_demo_api_requires_staff(client, customer_token, operator_token):
    assert client.get('/api/automotive/demo').status_code == 401
    assert client.get('/api/automotive/demo', headers={'Authorization': f'Bearer {customer_token}'}).status_code == 403
    result = client.get('/api/automotive/demo', headers={'Authorization': f'Bearer {operator_token}'})
    assert result.status_code == 200
    assert len(result.json()['preview']['decisions']) == 8


def test_preview_and_rehearsal_api(client, operator_token):
    headers = {'Authorization': f'Bearer {operator_token}'}
    response = client.post('/api/automotive/preview', headers=headers, json=demo_data(TODAY).model_dump(mode='json'))
    assert response.status_code == 200
    assert response.json()['summary']['ready'] == 2
    assert client.post('/api/automotive/rehearsal', headers=headers,
                       json={'vehicle_id': 'unknown', 'outcome': 'interested'}).status_code == 404
    assert client.post('/api/automotive/rehearsal', headers=headers,
                       json={'vehicle_id': 'demo-01', 'outcome': 'book_anyway'}).status_code == 422
    data = client.post('/api/automotive/rehearsal', headers=headers,
                       json={'vehicle_id': 'demo-01', 'outcome': 'opt_out'}).json()
    assert data['stage'] == 'suppression_required'
    assert not data['persisted']
