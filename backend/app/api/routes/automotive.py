"""Staff-only automotive previews and persistent local operations rehearsal."""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from app.automotive import roadside as rs
from app.automotive import whatsapp as wa
from app.core.config import get_settings
from app.core.webhook_security import verify_meta_signature
from app.api.dependencies import require_roles
from app.automotive.pilot import PreviewRequest, RehearsalRequest, demo_data, preview, rehearse
from app.models import RoleName, User

router = APIRouter(prefix='/automotive', tags=['automotive-pilot'])
staff = require_roles(RoleName.ADMIN, RoleName.OPERATOR)
logger = logging.getLogger('cognivault.automotive.routes')


@router.get('/demo')
def demo(user: User = Depends(staff)):
    data = demo_data()
    return {'input': data, 'preview': preview(data)}


@router.post('/preview')
def evaluate_records(body: PreviewRequest, user: User = Depends(staff)):
    # No tenant lookup: only the caller's supplied records are evaluated, never stored.
    return preview(body)


@router.post('/rehearsal')
def rehearsal(body: RehearsalRequest, user: User = Depends(staff)):
    try:
        return rehearse(body)
    except KeyError:
        raise HTTPException(status_code=404, detail='Demo aracı bulunamadı.') from None


# Local operations are persisted; external delivery remains disabled.
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.models import AutomotiveCase
from app.automotive import operations as ops
from app.automotive.channels import parse_meta_location, transfer_twiml
from pydantic import Field


@router.get('/operations/catalog')
def catalog(user: User = Depends(staff)):
    settings = get_settings()
    return {'services': ops.CATALOG, 'teams': ops.TEAMS, 'status_labels': ops.STATUS_LABELS,
            'mode': 'live' if settings.automotive_whatsapp_enabled else 'local_demo',
            'telephony_connected': settings.automotive_voice_enabled,
            'whatsapp_connected': settings.automotive_whatsapp_enabled,
            'simulator_enabled': not settings.automotive_whatsapp_enabled,
            'offer_timeout_minutes': int(rs.OFFER_TIMEOUT.total_seconds() // 60)}


@router.get('/operations/cases')
def list_cases(user: User = Depends(staff), db: Session = Depends(get_db)):
    rows = db.scalars(select(AutomotiveCase).where(*ops.scoped(user))
                      .order_by(AutomotiveCase.created_at.desc(), AutomotiveCase.id).limit(100)).all()
    return [ops.public(row) for row in rows]


@router.post('/operations/cases')
def create_case(body: ops.CreateCase, user: User = Depends(staff), db: Session = Depends(get_db)):
    return ops.create_case(db, user, body)


@router.get('/operations/cases/{case_id}')
def read_case(case_id: str, user: User = Depends(staff), db: Session = Depends(get_db)):
    return ops.public(ops.fetch(db, user, case_id))


@router.get('/operations/cases/{case_id}/teams')
def eligible_teams(case_id: str, user: User = Depends(staff), db: Session = Depends(get_db)):
    row = ops.fetch(db, user, case_id)
    occupied = set(db.scalars(select(AutomotiveCase.team_slot).where(
        *ops.scoped(user), AutomotiveCase.id != case_id, AutomotiveCase.team_slot.is_not(None))).all())
    return [team for team in ops.candidates(row.data) if team['id'] not in occupied]


@router.post('/operations/cases/{case_id}/actions')
def act(case_id: str, body: ops.Action, user: User = Depends(staff), db: Session = Depends(get_db)):
    return ops.act(db, user, case_id, body)


class LocationPreview(ops.StrictModel):
    event_key: str = Field(min_length=8, max_length=80)
    version: int = Field(ge=1)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    address: str = Field(default='', max_length=300)


@router.post('/operations/cases/{case_id}/whatsapp-location')
def simulate_location(case_id: str, body: LocationPreview, user: User = Depends(staff), db: Session = Depends(get_db)):
    # Authenticated provider-shaped rehearsal, NOT an unverified public webhook.
    payload = parse_meta_location({'id': body.event_key, 'type': 'location',
                                  'location': body.model_dump(include={'latitude', 'longitude', 'address'})})
    return ops.act(db, user, case_id, ops.Action(kind='location', version=body.version, **payload))


@router.get('/operations/phone-preview')
def phone_preview(user: User = Depends(staff)):
    return {'mode': 'preview', 'connected': False, 'twiml': transfer_twiml()}


from fastapi import Request
from fastapi.responses import PlainTextResponse, Response
from app.automotive import phone


@router.post('/webhooks/voice/incoming')
async def receive_automotive_call(request: Request):
    fields = phone.verify_request(request, await request.body())
    return Response(phone.response('incoming', fields), media_type='application/xml')


@router.post('/webhooks/voice/gather')
async def gather_automotive_call(request: Request, attempt: int = 1, db: Session = Depends(get_db)):
    fields = phone.verify_request(request, await request.body())
    attempt = min(max(attempt, 1), 2)
    outcome = None
    # Arama hiçbir koşulda düşmez: iş açılamazsa (sahip hesabı yok, CallSid yok,
    # beklenmeyen hata) arayan yine dispeçere aktarılır, yalnız kayıt açılmaz.
    if fields.get('CallSid'):
        try:
            owner = rs.inbound_owner(db)
            outcome = rs.handle_call(db, owner, call_sid=fields['CallSid'], caller=fields.get('From', ''),
                                     speech=fields.get('SpeechResult', '') or fields.get('Digits', ''),
                                     attempt=attempt)
        except HTTPException as exc:
            logger.warning('automotive.call.case_not_opened', extra={'reason': str(exc.detail)[:120]})
            db.rollback()
    if fields.get('Digits'):  # arayan tuşladı: doğrudan ekibe
        outcome = None if outcome is None or outcome.ask_again else outcome
    return Response(phone.call_reply(outcome, attempt=attempt), media_type='application/xml')


@router.post('/webhooks/voice/transfer-status')
async def automotive_transfer_status(request: Request):
    fields = phone.verify_request(request, await request.body())
    return Response(phone.response('status', fields), media_type='application/xml')


# ─── Yol yardımı hattı: WhatsApp webhook ─────────────────────────────────────
# Oto servis ayrı bir işletmedir: kendi Meta uygulaması, numarası ve sırrı var.
# Klinik tarafının /webhooks/whatsapp ucuyla karışmaz.


@router.get('/webhooks/whatsapp')
def verify_whatsapp_webhook(mode: str | None = Query(default=None, alias='hub.mode'),
                            token: str | None = Query(default=None, alias='hub.verify_token'),
                            challenge: str | None = Query(default=None, alias='hub.challenge')):
    expected = get_settings().automotive_meta_verify_token
    if mode == 'subscribe' and expected and token == expected:
        return PlainTextResponse(challenge or '')
    return PlainTextResponse('verification failed', status_code=403)


@router.post('/webhooks/whatsapp')
async def receive_whatsapp(request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    if not (settings.automotive_whatsapp_enabled and settings.automotive_meta_app_secret
            and settings.automotive_whatsapp_phone_number_id):
        raise HTTPException(503, 'Otomotiv WhatsApp hattı etkin değil.')
    raw = await request.body()
    if len(raw) > 256 * 1024:
        raise HTTPException(413, 'İstek çok büyük.')
    # İmza HER ZAMAN zorunlu: bu uç iş açar, ekibe teklif gönderir.
    if not verify_meta_signature(app_secret=settings.automotive_meta_app_secret, raw_body=raw,
                                 signature_header=request.headers.get('X-Hub-Signature-256')):
        raise HTTPException(401, 'Geçersiz sağlayıcı imzası.')
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(400, 'Geçersiz gövde.') from None
    inbound, statuses = wa.parse_webhook(payload, phone_number_id=settings.automotive_whatsapp_phone_number_id)
    owner = rs.inbound_owner(db)
    # Bir mesajın hatası partinin geri kalanını düşürmez; Meta tüm partiyi
    # tekrar gönderirse işlenmiş olanlar mesaj kimliğiyle atlanır.
    for message in inbound:
        try:
            team_id = rs.team_for_phone(message.sender)
            if team_id:
                rs.handle_team(db, owner, team_id, message)
            else:
                rs.handle_customer(db, owner, message)
        except HTTPException as exc:
            db.rollback()
            logger.warning('automotive.whatsapp.message_failed', extra={'reason': str(exc.detail)[:120]})
    for status in statuses:
        rs.apply_status(db, status)
    return {'received': len(inbound), 'statuses': len(statuses)}


# ─── Simülatör (yalnız demo modu) ────────────────────────────────────────────
# Gerçek numara yokken panelden müşteri ve çekici rolü oynanır; akış canlıdaki
# kodun AYNISINDAN geçer. Canlı gönderim açıkken KAPALIDIR: aksi halde operatör
# panelden herhangi bir numaraya gerçek mesaj attırabilirdi.


def _simulator_guard():
    if get_settings().automotive_whatsapp_enabled:
        raise HTTPException(409, 'Canlı WhatsApp açıkken simülatör kapalıdır.')


def _sim_id() -> str:
    return f'sim.{uuid4().hex}'


class SimCustomer(ops.StrictModel):
    phone: str = Field(pattern=r'^\+[1-9]\d{7,14}$')
    kind: Literal['text', 'location', 'reply'] = 'text'
    text: str = Field(default='', max_length=1200)
    reply_id: str = Field(default='', max_length=256)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    address: str = Field(default='', max_length=300)
    name: str = Field(default='', max_length=80)


class SimTeam(ops.StrictModel):
    team_id: str = Field(max_length=80)
    reply_id: str = Field(max_length=256)


class SimCall(ops.StrictModel):
    phone: str = Field(default='', max_length=20)
    speech: str = Field(default='', max_length=1200)
    call_sid: str = Field(default='', max_length=64)
    attempt: int = Field(default=1, ge=1, le=2)


@router.post('/operations/simulate/customer')
def simulate_customer(body: SimCustomer, user: User = Depends(staff), db: Session = Depends(get_db)):
    _simulator_guard()
    if body.kind == 'location' and (body.latitude is None or body.longitude is None):
        raise HTTPException(422, 'Konum için enlem ve boylam gerekli.')
    message = wa.Inbound(sender=body.phone, message_id=_sim_id(), kind=body.kind, text=body.text,
                         latitude=body.latitude, longitude=body.longitude, address=body.address,
                         reply_id=body.reply_id, name=body.name)
    result = rs.handle_customer(db, user, message)
    return {'case': result.case, 'replies': result.replies}


@router.post('/operations/simulate/team')
def simulate_team(body: SimTeam, user: User = Depends(staff), db: Session = Depends(get_db)):
    _simulator_guard()
    if body.team_id not in {t['id'] for t in ops.TEAMS}:
        raise HTTPException(404, 'Ekip bulunamadı.')
    message = wa.Inbound(sender=f'sim:{body.team_id}', message_id=_sim_id(), kind='reply', reply_id=body.reply_id)
    result = rs.handle_team(db, user, body.team_id, message)
    if result.case is None:
        raise HTTPException(404, 'Yanıt bir işe bağlanamadı.')
    return {'case': result.case}


@router.post('/operations/simulate/call')
def simulate_call(body: SimCall, user: User = Depends(staff), db: Session = Depends(get_db)):
    _simulator_guard()
    call_sid = body.call_sid or f'SIM{uuid4().hex[:20]}'
    outcome = rs.handle_call(db, user, call_sid=call_sid, caller=body.phone, speech=body.speech,
                             attempt=body.attempt)
    return {'call_sid': call_sid, 'say': outcome.say, 'transfer': outcome.transfer,
            'ask_again': outcome.ask_again, 'case': outcome.case}


@router.post('/operations/simulate/expire-offers')
def simulate_expire_offers(user: User = Depends(staff), db: Session = Depends(get_db)):
    """Demo: bekleyen tekliflerin süresi dolmuş gibi davran (yalnız kendi işlerin)."""
    _simulator_guard()
    later = datetime.now(timezone.utc) + rs.OFFER_TIMEOUT + timedelta(seconds=1)
    return {'expired': rs.sweep_expired_offers(db, now=later, owner=user)}


@router.get('/operations/cases/{case_id}/messages')
def case_messages(case_id: str, user: User = Depends(staff), db: Session = Depends(get_db)):
    return rs.case_messages(db, user, case_id)
