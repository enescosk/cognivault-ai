"""Staff-only automotive previews and persistent local operations rehearsal."""
from fastapi import APIRouter, Depends, HTTPException
from app.api.dependencies import require_roles
from app.automotive.pilot import PreviewRequest, RehearsalRequest, demo_data, preview, rehearse
from app.models import RoleName, User

router = APIRouter(prefix='/automotive', tags=['automotive-pilot'])
staff = require_roles(RoleName.ADMIN, RoleName.OPERATOR)


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
    return {'services': ops.CATALOG, 'teams': ops.TEAMS, 'status_labels': ops.STATUS_LABELS,
            'mode': 'local_demo', 'telephony_connected': False, 'whatsapp_connected': False}


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
from fastapi.responses import Response
from app.automotive import phone


@router.post('/webhooks/voice/incoming')
async def receive_automotive_call(request: Request):
    fields = phone.verify_request(request, await request.body())
    return Response(phone.response('incoming', fields), media_type='application/xml')


@router.post('/webhooks/voice/gather')
async def gather_automotive_call(request: Request):
    fields = phone.verify_request(request, await request.body())
    return Response(phone.response('gather', fields), media_type='application/xml')


@router.post('/webhooks/voice/transfer-status')
async def automotive_transfer_status(request: Request):
    fields = phone.verify_request(request, await request.body())
    return Response(phone.response('status', fields), media_type='application/xml')
