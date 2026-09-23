"""Yol yardımı hattı — telefon/WhatsApp → iş → otomatik ekip teklifi → çekici.

Korunan değişmezler (bu dosyanın asıl işi):
- Müşteriye "yola çıktı" yalnız ekip "Yola çıktım" dediğinde söylenir.
- Acil sinyal her aşamada akışı keser.
- Ekip yanıtı yalnız ayarlarda tanımlı ekip numarasından, yalnız o ekibe atanmış
  iş için geçerlidir; müşteri kabul butonunu taklit edemez.
- WhatsApp 24 saat kuralı: pencere kapalıyken şablon; şablon yoksa "gönderildi"
  denmez, iş danışmana düşer.
- Teslim edilemeyen ya da yanıtsız kalan teklif sıradaki ekibe geçer.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest
from sqlalchemy import select

from app.automotive import roadside as rs
from app.automotive import whatsapp as wa
from app.core.config import get_settings
from app.models import AutomotiveCase, AutomotiveMessage, OutboxEvent, User

CUSTOMER = '+905321112233'
OTHER_CUSTOMER = '+905324445566'
TEAM_01 = '+905300000001'
TEAM_02 = '+905300000002'
_ids = count(1)


@pytest.fixture
def owner(db_session):
    return db_session.scalar(select(User).where(User.email == 'operator@test.com'))


@pytest.fixture
def live(monkeypatch):
    """Canlı gönderim açık: ekip numaraları + şablonlar tanımlı."""
    s = get_settings()
    monkeypatch.setattr(s, 'automotive_whatsapp_enabled', True)
    monkeypatch.setattr(s, 'automotive_team_phones', json.dumps({'atlas-01': TEAM_01, 'atlas-02': TEAM_02}))
    monkeypatch.setattr(s, 'automotive_wa_template_customer_location', 'yol_yardim_konum')
    monkeypatch.setattr(s, 'automotive_wa_template_customer_update', 'yol_yardim_durum')
    monkeypatch.setattr(s, 'automotive_wa_template_team_offer', 'yol_yardim_is_teklifi')
    return s


def msg(sender=CUSTOMER, *, text='', reply='', lat=None, lon=None, name='Ayşe'):
    kind = 'location' if lat is not None else ('reply' if reply else 'text')
    return wa.Inbound(sender=sender, message_id=f'wamid.test{next(_ids)}', kind=kind, text=text,
                      latitude=lat, longitude=lon, reply_id=reply, name=name)


def customer(db, owner, **kwargs):
    return rs.handle_customer(db, owner, msg(**kwargs))


def team(db, owner, team_id, action, case_id, phone=TEAM_01):
    return rs.handle_team(db, owner, team_id, msg(phone, reply=f't:{action}:{case_id}'))


def out(db, case_id, audience=None):
    rows = db.scalars(select(AutomotiveMessage).where(
        AutomotiveMessage.case_id == case_id, AutomotiveMessage.direction == 'out'
    ).order_by(AutomotiveMessage.created_at, AutomotiveMessage.id)).all()
    return [m for m in rows if audience is None or m.audience == audience]


def purposes(db, case_id, audience=None):
    return [m.purpose for m in out(db, case_id, audience)]


def ready_tow(db, owner, sender=CUSTOMER):
    """WhatsApp'tan yazan müşteriyi teklif aşamasına kadar götürür."""
    r = customer(db, owner, sender=sender, text='Yolda kaldım, çekici lazım')
    customer(db, owner, sender=sender, reply='c:safe:ok')
    customer(db, owner, sender=sender, lat=41.01, lon=29.07)
    customer(db, owner, sender=sender, text='34 ABC 123 Fiat Egea')
    customer(db, owner, sender=sender, reply='c:dest:service')
    return customer(db, owner, sender=sender, reply='c:share:yes')


# ─── Anlama ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize('text,service', [
    ('Kaza yaptım, çekici lazım', 'accident'),
    ('Aracım çalışmıyor, çekici gerekiyor', 'tow'),
    ('Aküm bitti galiba', 'battery'),
    ('Lastiğim patladı', 'tire'),
    ('Benzinim bitti', 'fuel'),
    ('Elektrikli aracımın şarjı bitti', 'ev'),
    ('Anahtar içeride kaldı', 'locked'),
    ('Periyodik bakım istiyorum', 'maintenance'),
    ('Muayene öncesi kontrol', 'inspection'),
    ('Merhaba', None),
])
def test_detect_service(text, service):
    assert rs.detect_service(text) == service


# ─── WhatsApp'tan yazan müşteri: uçtan uca çekici ─────────────────────────────


def test_whatsapp_tow_end_to_end(db_session, owner):
    r = customer(db_session, owner, text='Yolda kaldım, çekici lazım')
    case_id = r.case['id']
    assert r.case['service'] == 'tow'
    assert purposes(db_session, case_id) == ['ask_safety']  # sorun anlaşıldı → güvenlik

    customer(db_session, owner, reply='c:safe:ok')
    assert purposes(db_session, case_id)[-1] == 'location_request'  # konum güvenlikten hemen sonra
    customer(db_session, owner, lat=41.01, lon=29.07)
    assert purposes(db_session, case_id)[-1] == 'ask_vehicle'
    customer(db_session, owner, text='34 ABC 123 Fiat Egea')
    assert purposes(db_session, case_id)[-1] == 'ask_destination'
    customer(db_session, owner, reply='c:dest:service')
    assert purposes(db_session, case_id)[-1] == 'ask_share'
    r = customer(db_session, owner, reply='c:share:yes')

    assert r.case['status'] == 'offered'
    assert r.case['assigned_team']['id'] == 'atlas-01'
    team_offer = out(db_session, case_id, 'team:atlas-01')[-1]
    assert team_offer.purpose == 'team_offer'
    assert 'Fiat Egea' in team_offer.body and '41.01,29.07' in team_offer.body
    buttons = team_offer.payload['content']['interactive']['action']['buttons']
    assert [b['reply']['id'] for b in buttons] == [f't:accept15:{case_id}', f't:accept30:{case_id}', f't:decline:{case_id}']

    r = team(db_session, owner, 'atlas-01', 'accept15', case_id)
    assert r.case['status'] == 'accepted' and r.case['eta_minutes'] == 15
    for step, status in [('en_route', 'en_route'), ('arrived', 'arrived'),
                         ('transport', 'transporting'), ('complete', 'completed')]:
        r = team(db_session, owner, 'atlas-01', step, case_id)
        assert r.case['status'] == status
    assert purposes(db_session, case_id, 'customer')[-5:] == ['accepted', 'en_route', 'arrived', 'transporting', 'completed']
    row = db_session.get(AutomotiveCase, case_id)
    assert row.team_slot is None  # kapanınca ekip serbest


def test_customer_never_hears_departed_before_team_says_so(db_session, owner):
    """"Yola çıktı" yalnız ekip "Yola çıktım" dedikten sonra."""
    r = ready_tow(db_session, owner)
    case_id = r.case['id']
    team(db_session, owner, 'atlas-01', 'accept30', case_id)
    before = [m.body for m in out(db_session, case_id, 'customer')]
    assert not any('yola çıktı' in body for body in before)
    assert any('Ekip yola çıkınca size haber vereceğiz' in body for body in before)
    team(db_session, owner, 'atlas-01', 'en_route', case_id)
    assert 'yola çıktı' in out(db_session, case_id, 'customer')[-1].body


def test_onsite_service_skips_destination_and_goes_to_mobile_team(db_session, owner):
    r = customer(db_session, owner, text='Aküm bitti, araba çalışmıyor')
    assert r.case['service'] == 'battery'
    customer(db_session, owner, reply='c:safe:ok')
    customer(db_session, owner, lat=41.02, lon=29.08)
    customer(db_session, owner, text='06 XYZ 42 Renault Clio')
    assert 'ask_destination' not in purposes(db_session, r.case['id'])
    r = customer(db_session, owner, reply='c:share:yes')
    assert r.case['status'] == 'offered'
    assert r.case['assigned_team']['id'] == 'atlas-02'
    assert r.case['destination'] == rs.ONSITE


def test_out_of_order_location_first_is_accepted(db_session, owner):
    """Müşteri sırayı bozup önce konum atarsa o soru atlanır."""
    r = customer(db_session, owner, text='Çekici lazım')
    customer(db_session, owner, lat=41.01, lon=29.07)
    r = customer(db_session, owner, reply='c:safe:ok')
    assert r.case['location'] is not None
    assert purposes(db_session, r.case['id'])[-1] == 'ask_vehicle'
    assert purposes(db_session, r.case['id']).count('location_request') == 0


def test_unknown_problem_is_asked_with_buttons(db_session, owner):
    r = customer(db_session, owner, text='Merhaba')
    assert purposes(db_session, r.case['id']) == ['ask_problem']
    r = customer(db_session, owner, reply='c:svc:tire')
    assert r.case['service'] == 'tire'
    assert purposes(db_session, r.case['id'])[-1] == 'ask_safety'


def test_workshop_request_skips_roadside_questions(db_session, owner):
    r = customer(db_session, owner, text='Periyodik bakım randevusu istiyorum')
    assert r.case['service'] == 'maintenance'
    assert purposes(db_session, r.case['id']) == ['ask_vehicle']  # güvenlik/konum sorulmaz
    r = customer(db_session, owner, text='34 KLM 55 Toyota Corolla')
    assert r.case['status'] == 'service_requested'
    assert 'danışmanı' in out(db_session, r.case['id'], 'customer')[-1].body


# ─── Güvenlik ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize('text', ['Kaza yaptık yaralı var', 'Araçtan duman çıkıyor yanıyor', 'Aracın içinde sıkıştım'])
def test_emergency_interrupts_at_intake(db_session, owner, text):
    r = customer(db_session, owner, text=text)
    assert r.case['status'] == 'emergency'
    assert '112' in r.replies[0]


def test_emergency_interrupts_during_dispatch(db_session, owner):
    r = ready_tow(db_session, owner)
    team(db_session, owner, 'atlas-01', 'accept15', r.case['id'])
    r = customer(db_session, owner, text='Arkadaşım yaralandı')
    assert r.case['status'] == 'emergency'


def test_danger_button_is_emergency(db_session, owner):
    customer(db_session, owner, text='Çekici lazım')
    r = customer(db_session, owner, reply='c:safe:danger')
    assert r.case['status'] == 'emergency'


def test_lane_hazard_raises_priority_and_advises(db_session, owner):
    customer(db_session, owner, text='Çekici lazım')
    r = customer(db_session, owner, reply='c:safe:lane')
    assert r.case['priority'] == 'high'
    assert 'bariyer' in ' '.join(r.replies)
    customer(db_session, owner, lat=41.01, lon=29.07)
    customer(db_session, owner, text='34 ABC 123 Fiat Egea')
    customer(db_session, owner, reply='c:dest:service')
    r = customer(db_session, owner, reply='c:share:yes')
    assert 'ÖNCELİKLİ' in out(db_session, r.case['id'], 'team:atlas-01')[-1].body


def test_refusing_to_share_location_goes_to_human(db_session, owner):
    customer(db_session, owner, text='Çekici lazım')
    customer(db_session, owner, reply='c:safe:ok')
    customer(db_session, owner, lat=41.01, lon=29.07)
    customer(db_session, owner, text='34 ABC 123')
    customer(db_session, owner, reply='c:dest:service')
    r = customer(db_session, owner, reply='c:share:no')
    assert r.case['status'] == 'human'
    assert r.case['assigned_team'] is None


# ─── Ekip: yetki ve yarış ────────────────────────────────────────────────────


def test_customer_cannot_forge_team_acceptance(db_session, owner):
    """Müşteri numarasından gelen "kabul" kimliği müşteri olayı sayılır, iş ilerlemez."""
    r = ready_tow(db_session, owner)
    forged = customer(db_session, owner, reply=f"t:accept15:{r.case['id']}")
    assert forged.case['status'] == 'offered'


def test_unassigned_team_cannot_advance(db_session, owner):
    r = ready_tow(db_session, owner)
    result = team(db_session, owner, 'atlas-02', 'accept15', r.case['id'], phone=TEAM_02)
    assert result.case['status'] == 'offered'
    assert out(db_session, r.case['id'], 'team:atlas-02')[-1].purpose == 'not_assigned'


def test_duplicate_webhook_is_processed_once(db_session, owner):
    inbound = msg(text='Çekici lazım')
    rs.handle_customer(db_session, owner, inbound)
    again = rs.handle_customer(db_session, owner, inbound)
    assert again.case is None
    assert db_session.scalar(select(AutomotiveCase).where(AutomotiveCase.owner_id == owner.id)).version == 2


def test_decline_with_no_other_team_goes_to_human(db_session, owner):
    """atlas-03 servis dışı; atlas-01 reddedince uygun çekici kalmaz."""
    r = ready_tow(db_session, owner)
    r = team(db_session, owner, 'atlas-01', 'decline', r.case['id'])
    assert r.case['status'] == 'human'
    assert out(db_session, r.case['id'], 'customer')[-1].purpose == 'no_team'


def test_busy_team_is_not_offered_twice(db_session, owner):
    first = ready_tow(db_session, owner, sender=CUSTOMER)
    assert first.case['status'] == 'offered'
    second = ready_tow(db_session, owner, sender=OTHER_CUSTOMER)
    assert second.case['status'] == 'human'  # atlas-01 dolu, diğer çekici servis dışı


# ─── Zaman aşımı ─────────────────────────────────────────────────────────────


def test_offer_times_out_and_escalates(db_session, owner):
    r = ready_tow(db_session, owner)
    now = datetime.now(timezone.utc)
    assert rs.sweep_expired_offers(db_session, now=now + timedelta(minutes=2)) == 0
    assert rs.sweep_expired_offers(db_session, now=now + timedelta(minutes=6)) == 1
    row = db_session.get(AutomotiveCase, r.case['id'])
    db_session.refresh(row)
    assert row.data['status'] == 'human'
    assert 'atlas-01' in row.data['declined_teams']
    assert out(db_session, r.case['id'], 'team:atlas-01')[-1].purpose == 'offer_withdrawn'


def test_late_acceptance_after_timeout_is_rejected(db_session, owner):
    r = ready_tow(db_session, owner)
    rs.sweep_expired_offers(db_session, now=datetime.now(timezone.utc) + timedelta(minutes=6))
    late = team(db_session, owner, 'atlas-01', 'accept15', r.case['id'])
    assert late.case['status'] == 'human'
    # Zaman aşımı geleceğe enjekte edildiği için sırasına değil varlığına bakılır.
    assert 'not_assigned' in purposes(db_session, r.case['id'], 'team:atlas-01')


# ─── Sevk sonrası müşteri mesajları ──────────────────────────────────────────


def test_where_is_it_answers_with_eta(db_session, owner):
    r = ready_tow(db_session, owner)
    team(db_session, owner, 'atlas-01', 'accept30', r.case['id'])
    r = customer(db_session, owner, text='Çekici nerede kaldı?')
    assert '30 dakika' in r.replies[-1]


def test_cancel_before_acceptance_frees_team(db_session, owner):
    r = ready_tow(db_session, owner)
    r = customer(db_session, owner, text='İptal edin, hallettim')
    assert r.case['status'] == 'cancelled'
    assert out(db_session, r.case['id'], 'team:atlas-01')[-1].purpose == 'offer_cancelled'
    assert db_session.get(AutomotiveCase, r.case['id']).team_slot is None


def test_cancel_after_acceptance_needs_human(db_session, owner):
    r = ready_tow(db_session, owner)
    team(db_session, owner, 'atlas-01', 'accept15', r.case['id'])
    r = customer(db_session, owner, text='Vazgeçtim iptal')
    assert r.case['status'] == 'human'
    assert 'otomatik iptal edilmedi' in r.replies[-1]


def test_location_change_after_dispatch_is_not_applied(db_session, owner):
    r = ready_tow(db_session, owner)
    team(db_session, owner, 'atlas-01', 'accept15', r.case['id'])
    r = customer(db_session, owner, lat=40.5, lon=28.5)
    assert r.case['location']['latitude'] == 41.01
    assert r.case['status'] == 'accepted'


# ─── Telefon ─────────────────────────────────────────────────────────────────


def test_call_opens_case_and_does_not_claim_whatsapp_in_demo(db_session, owner):
    outcome = rs.handle_call(db_session, owner, call_sid='CA1', caller=CUSTOMER,
                             speech='Aracım çalışmıyor, çekici lazım')
    assert outcome.transfer and outcome.case['service'] == 'tow'
    assert 'WhatsApp' not in outcome.say  # gönderim kapalıyken "gönderdik" denmez
    message = out(db_session, outcome.case['id'], 'customer')[0]
    assert message.purpose == 'location_request' and message.delivery_status == 'demo_only'


def test_call_with_live_whatsapp_uses_template_and_says_so(db_session, owner, live):
    outcome = rs.handle_call(db_session, owner, call_sid='CA2', caller=CUSTOMER, speech='Lastiğim patladı')
    message = out(db_session, outcome.case['id'], 'customer')[0]
    assert message.form == 'template'  # müşteri hiç yazmadı → 24 saat penceresi kapalı
    assert message.delivery_status == 'queued'
    assert message.payload['content']['template']['name'] == 'yol_yardim_konum'
    assert db_session.get(OutboxEvent, message.outbox_event_id).event_type == rs.OUTBOX_EVENT
    assert 'WhatsApp' in outcome.say


def test_call_without_template_escalates_instead_of_claiming(db_session, owner, live, monkeypatch):
    monkeypatch.setattr(get_settings(), 'automotive_wa_template_customer_location', '')
    outcome = rs.handle_call(db_session, owner, call_sid='CA3', caller=CUSTOMER, speech='Çekici lazım')
    message = out(db_session, outcome.case['id'], 'customer')[0]
    assert message.delivery_status == 'blocked_no_template'
    assert 'WhatsApp' not in outcome.say
    row = db_session.get(AutomotiveCase, outcome.case['id'])
    db_session.refresh(row)
    assert row.data['status'] == 'human'


def test_template_tap_opens_window_then_location_request_is_session(db_session, owner, live):
    outcome = rs.handle_call(db_session, owner, call_sid='CA4', caller=CUSTOMER, speech='Çekici lazım')
    r = customer(db_session, owner, reply='c:loc:ready')
    assert r.case['id'] == outcome.case['id']
    request = out(db_session, r.case['id'], 'customer')[-1]
    assert request.purpose == 'location_request' and request.form == 'session'
    assert request.payload['content']['interactive']['type'] == 'location_request_message'


def test_unclear_call_is_asked_once_then_defaults_to_tow(db_session, owner):
    first = rs.handle_call(db_session, owner, call_sid='CA5', caller=CUSTOMER, speech='Şey, merhaba')
    assert first.ask_again and first.case is None
    second = rs.handle_call(db_session, owner, call_sid='CA5', caller=CUSTOMER, speech='Bilmiyorum', attempt=2)
    assert second.case['service'] == 'tow'


def test_emergency_call_is_flagged_and_transferred(db_session, owner):
    outcome = rs.handle_call(db_session, owner, call_sid='CA6', caller=CUSTOMER, speech='Kaza oldu yaralı var')
    assert outcome.case['status'] == 'emergency'
    assert '112' in outcome.say and outcome.transfer


def test_repeated_call_webhook_does_not_resend(db_session, owner):
    rs.handle_call(db_session, owner, call_sid='CA7', caller=CUSTOMER, speech='Çekici lazım')
    again = rs.handle_call(db_session, owner, call_sid='CA7', caller=CUSTOMER, speech='Çekici lazım')
    assert len(out(db_session, again.case['id'], 'customer')) == 1


def test_withheld_caller_still_gets_a_case(db_session, owner):
    outcome = rs.handle_call(db_session, owner, call_sid='CA8', caller='anonymous', speech='Çekici lazım')
    assert outcome.case['status'] == 'intake'
    assert out(db_session, outcome.case['id']) == []  # numara yok → mesaj yok, dispeçer konuşuyor


# ─── Canlı gönderim: şablon, teslim, hata ────────────────────────────────────


def test_first_team_offer_uses_template_then_session_after_reply(db_session, owner, live):
    r = ready_tow(db_session, owner)
    offer = out(db_session, r.case['id'], 'team:atlas-01')[-1]
    assert offer.form == 'template' and offer.delivery_status == 'queued'
    quick = [c['parameters'][0]['payload'] for c in offer.payload['content']['template']['components']
             if c['type'] == 'button']
    assert quick[0] == f"t:accept15:{r.case['id']}"
    team(db_session, owner, 'atlas-01', 'accept15', r.case['id'])
    after = out(db_session, r.case['id'], 'team:atlas-01')
    assert {m.form for m in after if m.purpose in {'team_location', 'team_next'}} == {'session'}


def test_delivery_handler_marks_accepted(db_session, owner, live, monkeypatch):
    r = ready_tow(db_session, owner)
    offer = out(db_session, r.case['id'], 'team:atlas-01')[-1]
    sent = []
    monkeypatch.setattr(wa, 'send', lambda message, client=None: sent.append(message) or 'wamid.OUT1')
    deliver = rs.make_delivery_handler(lambda: _NoClose(db_session))
    deliver(db_session.get(OutboxEvent, offer.outbox_event_id))
    db_session.refresh(offer)
    assert offer.delivery_status == 'accepted' and offer.provider_message_id == 'wamid.OUT1'
    assert sent[0]['to'] == TEAM_01[1:]

    rs.apply_status(db_session, wa.StatusUpdate('wamid.OUT1', 'read'))
    rs.apply_status(db_session, wa.StatusUpdate('wamid.OUT1', 'delivered'))  # sıra dışı
    db_session.refresh(offer)
    assert offer.delivery_status == 'read'


def test_undeliverable_team_offer_moves_on(db_session, owner, live, monkeypatch):
    r = ready_tow(db_session, owner)
    offer = out(db_session, r.case['id'], 'team:atlas-01')[-1]

    def reject(message, client=None):
        raise wa.PermanentSendError('400 Template not approved')
    monkeypatch.setattr(wa, 'send', reject)
    rs.make_delivery_handler(lambda: _NoClose(db_session))(db_session.get(OutboxEvent, offer.outbox_event_id))
    db_session.refresh(offer)
    assert offer.delivery_status == 'failed'
    row = db_session.get(AutomotiveCase, r.case['id'])
    db_session.refresh(row)
    assert row.data['status'] == 'human'  # tek çekici vardı, teklif gitmedi → danışman


def test_status_webhook_failure_on_team_offer_moves_on(db_session, owner, live, monkeypatch):
    r = ready_tow(db_session, owner)
    offer = out(db_session, r.case['id'], 'team:atlas-01')[-1]
    offer.provider_message_id, offer.delivery_status = 'wamid.OUT2', 'accepted'
    db_session.commit()
    rs.apply_status(db_session, wa.StatusUpdate('wamid.OUT2', 'failed', 'Recipient not on WhatsApp'))
    row = db_session.get(AutomotiveCase, r.case['id'])
    db_session.refresh(row)
    assert row.data['status'] == 'human'


def test_team_phone_mapping_rejects_unknown_and_malformed(monkeypatch):
    monkeypatch.setattr(get_settings(), 'automotive_team_phones',
                        json.dumps({'atlas-01': TEAM_01, 'atlas-99': TEAM_02, 'atlas-02': '0530'}))
    assert rs.team_phones() == {'atlas-01': TEAM_01}
    assert rs.team_for_phone(TEAM_01) == 'atlas-01'
    assert rs.team_for_phone(CUSTOMER) is None


def test_panel_masks_customer_number(db_session, owner):
    r = customer(db_session, owner, text='Çekici lazım')
    assert CUSTOMER not in json.dumps(r.case)
    assert r.case['contact'].endswith('2233')


class _NoClose:
    """Handler kendi oturumunu `with` ile açar; testte aynı oturumu kapatmadan ver."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False
