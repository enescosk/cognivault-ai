from __future__ import annotations

from typing import Literal
import io
import wave
import time
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, SecretStr
from starlette.concurrency import run_in_threadpool

from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_roles
from app.models import RoleName, User
from app.core.config import get_settings
from app.ai.voice_factory import _get_whisper, resolve_voice_profile
from app.services import voice_studio_service as svc
from app.services.clinical_service import ensure_clinic_access
from app.services.voice_profile import (ALLOWED_MODELS, ROLES, apply_profile, call_readiness,
                                        clinic_voice_profile, normalize_profile)

router = APIRouter(prefix='/voice-studio', tags=['voice-studio'])
staff = require_roles(RoleName.ADMIN, RoleName.OPERATOR)


class Connection(BaseModel):
    api_key: SecretStr = Field(min_length=10, max_length=512)


class Turn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class VoiceCharacter(BaseModel):
    """Stüdyoda ayarlanan ses karakteri. Canlı çağrı yolu ile birebir aynı alanlar."""

    voice_id: str = Field(default='local-piper', pattern=r'^[A-Za-z0-9_-]{1,100}$')
    model: Literal[ALLOWED_MODELS] = 'eleven_multilingual_v2'  # type: ignore[valid-type]
    speed: float = Field(default=1.0, ge=0.7, le=1.2)
    stability: float = Field(default=0.45, ge=0.0, le=1.0)
    similarity_boost: float = Field(default=0.80, ge=0.0, le=1.0)
    style: float = Field(default=0.0, ge=0.0, le=1.0)
    speaker_boost: bool = True


class Speech(VoiceCharacter):
    text: str = Field(min_length=1, max_length=1800)
    provider: Literal['local', 'elevenlabs'] = 'elevenlabs'
    cloud_consent: bool = False


@router.get('/status')
def status(user: User = Depends(staff)):
    return {'connected': bool(svc.connection_key(user.id)), 'llm_model': get_settings().local_llm_model,
            'telephony_connected': False, 'mode': 'rehearsal'}


@router.post('/connection')
def connect(body: Connection, user: User = Depends(staff)):
    key = body.api_key.get_secret_value().strip()
    result = svc.voices(key)
    svc.connections[user.id] = (key, time.monotonic())
    return result


@router.delete('/connection')
def disconnect(user: User = Depends(staff)):
    svc.connections.pop(user.id, None)
    return {'connected': bool(svc.connection_key(user.id))}


@router.get('/voices')
def voices(search: str = Query('', max_length=100), page_token: str | None = Query(None, max_length=512), user: User = Depends(staff)):
    return svc.voices(svc.connection_key(user.id), search, page_token)


@router.post('/sessions')
def start(body: svc.Scenario, user: User = Depends(staff)):
    s = svc.start_session(user.id, body)
    return {'id': s.id, 'reply': s.messages[0]['content'], 'stage': s.stage, 'source': 'karşılama'}


@router.post('/sessions/{session_id}/messages')
def message(session_id: str, body: Turn, user: User = Depends(staff)):
    s = svc.owned_session(session_id, user.id)
    if not body.text.strip():
        raise HTTPException(422, 'Mesaj boş olamaz.')
    if not s.lock.acquire(blocking=False):
        raise HTTPException(409, 'Önceki yanıt hazırlanıyor; lütfen bekleyin.')
    try:
        return svc.advance(s, body.text.strip())
    finally:
        s.lock.release()


@router.post('/speech')
def speech(body: Speech, user: User = Depends(staff)):
    if body.provider == 'local':
        from app.ai.voice_factory import _get_piper
        from piper.config import SynthesisConfig
        try:
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as output:
                _get_piper().synthesize_wav(body.text, output, syn_config=SynthesisConfig(length_scale=1 / body.speed))
            return Response(buffer.getvalue(), media_type='audio/wav', headers={'Cache-Control': 'no-store'})
        except Exception:
            raise HTTPException(503, 'Yerel Piper sesi hazır değil. ElevenLabs hesabını bağlayabilir veya yazıyla devam edebilirsiniz.') from None
    if not body.cloud_consent:
        raise HTTPException(403, 'Seslendirme için ElevenLabs işleme seçimini açın.')
    profile = resolve_voice_profile(body.model_dump(exclude={'text', 'provider', 'cloud_consent'}))
    response = svc.eleven_request('POST', '/v1/text-to-speech/' + profile.voice_id,
        svc.connection_key(user.id), params={'output_format': profile.output_format},
        json=profile.payload(body.text))
    return Response(response.content, media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})


def _profile_state(clinic, user: User) -> dict:
    """Kliniğin iki tarafının sesi + her biri için canlıya çıkışın önündeki engeller."""
    settings_json = clinic.settings_json or {}
    voice = settings_json.get('voice') or {}
    app_settings = get_settings()
    server_key = bool(app_settings.elevenlabs_api_key)
    roles = {}
    for role in ROLES:
        blockers = call_readiness(settings_json, server_key_configured=server_key,
                                  app_external_enabled=bool(app_settings.voice_external_enabled),
                                  role=role)
        roles[role] = {'profile': clinic_voice_profile(voice, role),
                       'live': not blockers, 'blockers': blockers}
    return {'clinic': clinic.slug, 'roles': roles,
            'tts_provider': voice.get('tts_provider') or 'local',
            'external_enabled': bool(voice.get('external_enabled', False)),
            'server_key_configured': server_key,
            # Ses seçimi operatörün işi; sesi canlıya almak (sınır-ötesi işleme)
            # yönetici kararı. Arayüz düğmeyi buna göre gösterir.
            'can_go_live': user.role.name == RoleName.ADMIN}


@router.get('/profile')
def read_profile(db: Session = Depends(get_db), user: User = Depends(staff)):
    """Kliniğin karşılayan ve arayan asistanlarının ses karakterleri."""
    return _profile_state(ensure_clinic_access(db, user), user)


class ProfileUpdate(VoiceCharacter):
    role: Literal[ROLES] = 'receiver'  # type: ignore[valid-type]
    # Sesi canlıya almak sınır-ötesi işleme kararıdır: açıkça istenmeden
    # kliniğin sağlayıcısı değiştirilmez (KVKK kapısı yerinde kalır).
    use_in_calls: bool = False


@router.put('/profile')
def save_profile(body: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(staff)):
    """Seçilen sesi kliniğin ilgili tarafına (karşılayan/arayan) kaydeder.

    Kaydı operatör de yapabilir; `use_in_calls` ile sınır-ötesi işlemeyi açmak
    yalnızca yöneticinin yetkisindedir.
    """
    if body.use_in_calls and user.role.name != RoleName.ADMIN:
        raise HTTPException(403, 'Sesi canlı görüşmelere almak yönetici yetkisi gerektirir. '
                                 'Ses seçimini kaydedebilir, canlıya alınmasını yöneticiden isteyebilirsiniz.')
    clinic = ensure_clinic_access(db, user)
    profile = normalize_profile(body.model_dump(exclude={'use_in_calls', 'role'}))
    if body.use_in_calls and not profile.get('voice_id'):
        raise HTTPException(422, 'Canlı çağrılar için önce bir ElevenLabs sesi seçin.')
    clinic.settings_json = apply_profile(
        clinic.settings_json, profile, role=body.role,
        tts_provider='elevenlabs' if body.use_in_calls else None,
        external_enabled=True if body.use_in_calls else None,
        allow_cross_border=True if body.use_in_calls else None,
    )
    db.add(clinic)
    db.commit()
    db.refresh(clinic)
    return _profile_state(clinic, user)


@router.post('/transcribe')
async def transcribe(file: UploadFile = File(...), provider: Literal['local', 'elevenlabs'] = Form('local'),
                     cloud_consent: bool = Form(False), user: User = Depends(staff)):
    audio = await file.read(8 * 1024 * 1024 + 1)
    if not audio or len(audio) > 8 * 1024 * 1024:
        raise HTTPException(413, 'Ses kaydı boş veya 8 MB sınırını aşıyor.')
    started = time.monotonic()
    def decode():
        if provider == 'elevenlabs':
            if not cloud_consent:
                raise HTTPException(403, 'Ses tanıma için ElevenLabs işleme seçimini açın.')
            data = svc.eleven_request('POST', '/v1/speech-to-text', svc.connection_key(user.id),
                 data={'model_id': 'scribe_v2', 'language_code': 'tur', 'tag_audio_events': 'false', 'diarize': 'false'},
                 files={'file': ('speech.webm', audio, file.content_type or 'audio/webm')}).json()
            return {'text': data.get('text', '').strip(), 'confidence': None}
        import io
        try:
            segments, _ = _get_whisper().transcribe(io.BytesIO(audio), language='tr', beam_size=5,
                temperature=0, vad_filter=True, condition_on_previous_text=False,
                initial_prompt='Türkçe şirket görüşmesi. Merhaba, CogniVault, randevu, mesaj, yetkili, tanışma toplantısı.')
            items = list(segments)
            from app.ai.voice_factory import _estimate_whisper_confidence
            return {'text': ''.join(s.text for s in items).strip(), 'confidence': _estimate_whisper_confidence(items)}
        except Exception:
            raise HTTPException(502, 'Yerel ses tanıma başarısız oldu. Tekrar konuşabilir veya metinle devam edebilirsiniz.') from None
    result = await run_in_threadpool(decode)
    return {**result, 'provider': provider, 'processing_ms': round((time.monotonic() - started) * 1000)}
