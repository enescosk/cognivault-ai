"""Astra receptionist regression tests; providers are mocked."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from app.ai.astra import AstraProvider
from app.ai.ai_factory import get_llm_provider, LocalQwenProvider
from app.core.config import Settings, get_settings
from app.models import Clinic, ClinicIntent, ClinicChannel, ConsentRecord, ConsentType
from app.services import clinical_ai_service as ai
from app.services import medical_triage_service as medical
from app.services.clinical_consent import has_active_consent
from app.services.clinical_persona_service import get_persona


def clinic():
    return Clinic(name='Synthetic', slug='synthetic', default_language='tr', ai_auto_reply_threshold=.9,
                  settings_json={'allow_cross_border_processors': True, 'data_residency_mode': 'hybrid'})


def payload(**kw):
    return dict(reply='Hangi saat aralığı uygun?', confidence=.93, intent='book_appointment',
                requires_human_review=False, risk_reason=None, **kw)


@pytest.fixture
def configured(monkeypatch):
    s = get_settings()
    for k, v in dict(openai_api_key='fake', clinical_ai_enabled=True,
                     clinical_external_ai_allowed=True, clinical_llm_provider='astra').items():
        monkeypatch.setattr(s, k, v)
    return s


def test_responses_contract(configured, monkeypatch):
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.responses.create.return_value = SimpleNamespace(status='completed', output_text=json.dumps(payload()), usage=None)
    monkeypatch.setattr('app.ai.astra.OpenAI', factory)
    assert AstraProvider().generate_chat_reply('Synthetic')['data']['draft_only']
    args = client.responses.create.call_args.kwargs
    assert args['model'] == 'gpt-6-astra' and args['store'] is False
    assert args['text']['format']['strict']
    assert 'temperature' not in args and 'tools' not in args
    assert factory.call_args.kwargs['max_retries'] == 0
    for status, output in [('incomplete', json.dumps(payload())), ('completed', '[]'), ('completed', '{}')]:
        client.responses.create.return_value = SimpleNamespace(status=status, output_text=output, usage=None)
        assert AstraProvider().generate_chat_reply('test') is None
    client.responses.create.side_effect = TimeoutError()
    assert AstraProvider().generate_chat_reply('test') is None


def test_provider_gates(configured, monkeypatch):
    assert isinstance(get_llm_provider('hybrid', True), AstraProvider)
    assert isinstance(get_llm_provider('hybrid', False), LocalQwenProvider)
    monkeypatch.setattr(configured, 'clinical_external_ai_allowed', False)
    assert isinstance(get_llm_provider('hybrid', True), LocalQwenProvider)


@pytest.mark.parametrize('text', ['Merhaba', 'Teşekkürler', 'Orada mısın?', 'Sen kimsin?', 'Thanks'])
def test_social_stays_local(configured, monkeypatch, text):
    provider = MagicMock(side_effect=AssertionError('must stay local'))
    monkeypatch.setattr(ai, 'get_llm_provider', provider)
    assert ai.generate_clinical_reply(clinic(), text).action == 'greeting_reception'
    provider.assert_not_called()


def test_greeting_continuity_and_real_requests():
    result = ai.generate_clinical_reply(clinic(), 'Merhaba', use_ai=False, already_greeted=True)
    assert 'asistan' not in result.reply.lower()
    result = ai.generate_clinical_reply(clinic(), 'Teşekkürler, randevumu iptal etmek istiyorum', use_ai=False)
    assert result.intent == ClinicIntent.CANCEL_APPOINTMENT


def test_context_and_masking(configured, monkeypatch):
    provider = MagicMock()
    provider.generate_chat_reply.return_value = {**payload(), '_provider_source': 'openai_astra'}
    monkeypatch.setattr(ai, 'get_llm_provider', lambda *a: provider)
    history = [{'role': 'user', 'content': 'old-marker'}] + [
        {'role': 'user', 'content': 'Salı için randevu. Telefon 05551234567'} for _ in range(6)]
    result = ai.generate_clinical_reply(clinic(), 'Perşembe olsun', previous_intent=ClinicIntent.BOOK_APPOINTMENT,
                                       external_ai_consent=True, conversation_history=history)
    prompt = provider.generate_chat_reply.call_args.args[0]
    assert 'Salı' in prompt and 'Perşembe' in prompt
    assert '05551234567' not in prompt and 'old-marker' not in prompt
    assert result.intent == ClinicIntent.BOOK_APPOINTMENT


@pytest.mark.parametrize('enabled,consent', [(False, False), (False, True), (True, False)])
def test_medical_consent(configured, monkeypatch, enabled, consent):
    monkeypatch.setattr(configured, 'clinical_llm_provider', 'auto')
    factory = MagicMock(side_effect=AssertionError('blocked'))
    monkeypatch.setattr(medical, 'OpenAI', factory)
    assert medical.assess_medical_triage(clinic(), 'diş ağrısı', 'tr', use_ai=enabled,
                                         external_ai_consent=consent).source == 'rules'
    factory.assert_not_called()


def test_emergency_never_uses_model(configured, monkeypatch):
    factory = MagicMock(side_effect=AssertionError('blocked'))
    monkeypatch.setattr(medical, 'OpenAI', factory)
    result = ai.generate_clinical_reply(clinic(), 'Merhaba nefes alamıyorum', external_ai_consent=True)
    assert result.requires_human_review and '112' in result.reply
    factory.assert_not_called()


@pytest.mark.parametrize('reply', ['Randevunuzu oluşturdum.', 'Your appointment is confirmed.', 'Mesajınız gönderildi.'])
def test_false_completion_claim(reply):
    p = payload(); p['reply'] = reply
    result = ai._validated_provider_result(p, deterministic_intent=ClinicIntent.BOOK_APPOINTMENT,
        deterministic_confidence=.9, language='tr', clinic=clinic(), persona=get_persona('selin'))
    assert result.requires_human_review and result.risk_reason == 'unverified_model_action_claim'


def test_ingestion_context_and_revoked_consent(db_session):
    from app.services.clinical_service import ensure_default_clinic, ingest_clinical_message, IncomingClinicalMessage
    c = ensure_default_clinic(db_session)
    def send(phone):
        return ingest_clinical_message(db_session, IncomingClinicalMessage(
            from_phone=phone, body='Merhaba', channel=ClinicChannel.WHATSAPP), clinic=c, use_ai=False)
    first, again, other = send('+905550000001'), send('+905550000001'), send('+905550000002')
    assert 'asistan' in first.reply.lower() and 'asistan' not in again.reply.lower()
    assert 'asistan' in other.reply.lower()
    scope = dict(clinic_id=c.id, patient_id=first.patient.id, conversation_id=first.conversation.id,
                 consent_type=ConsentType.CROSS_BORDER_TRANSFER)
    now = datetime.now(timezone.utc)
    db_session.add(ConsentRecord(**scope, granted=True, granted_at=now-timedelta(seconds=1), consent_text_version='test'))
    db_session.commit()
    assert has_active_consent(db_session, **scope)
    db_session.add(ConsentRecord(**scope, granted=False, granted_at=now, consent_text_version='test'))
    db_session.commit()
    assert not has_active_consent(db_session, **scope)


def test_ingestion_passes_verified_consent_to_astra(db_session, configured, monkeypatch):
    from app.services.clinical_service import ensure_default_clinic, ingest_clinical_message, IncomingClinicalMessage
    c = ensure_default_clinic(db_session)
    c.settings_json = {**(c.settings_json or {}), 'allow_cross_border_processors': True,
                       'data_residency_mode': 'hybrid'}
    db_session.commit()
    def send(body):
        return ingest_clinical_message(db_session, IncomingClinicalMessage(
            from_phone='+905550000008', body=body, channel=ClinicChannel.WHATSAPP), clinic=c)
    first = send('Merhaba')
    db_session.add(ConsentRecord(clinic_id=c.id, patient_id=first.patient.id,
        conversation_id=first.conversation.id, consent_type=ConsentType.CROSS_BORDER_TRANSFER,
        granted=True, consent_text_version='test'))
    db_session.commit()
    draft = payload(); draft['intent'] = 'ask_location'; draft['reply'] = 'Hangi şubenin adresini öğrenmek istersiniz?'
    provider = MagicMock(return_value={**draft, '_provider_source': 'openai_astra'})
    monkeypatch.setattr(AstraProvider, 'generate_chat_reply', provider)
    send('Adresiniz nerede?')
    provider.assert_called_once()
    assert 'Merhaba' in provider.call_args.args[0]


# --- Codex devralma düzeltmeleri (2026-09-15) -------------------------------
# Dördü de canlı hasta yolunu etkiliyordu; her biri kanıtla bulundu.


@pytest.mark.parametrize('text', ['apse', 'apse oluştu', 'ateşim çıktı', 'yanağım şişti', 'kaşıntı var'])
@pytest.mark.parametrize('previous', [ClinicIntent.ASK_PRICE, ClinicIntent.BOOK_APPOINTMENT])
def test_medical_escalation_outranks_context_carry(text, previous):
    """Semptom mesajı, önceki turun ticari niyetini miras almamalı.

    Bağlam taşıma 3 kelimeden kısa HER mesaja uygulandığı için, önceki tur fiyat
    sorusuyken gelen "apse" fiyat cevabı alıyordu. Yükseltme artık taşımanın
    önünde çalışıyor ve UNKNOWN'ı da kapsıyor.
    """
    # Testin öncülü: bu metinler bağlamsız olarak zaten belirsiz sınıflanıyor —
    # düzeltmenin yönettiği aralık tam olarak burası.
    assert ai.classify_intent(text)[0] in {ClinicIntent.GENERAL_QUESTION, ClinicIntent.UNKNOWN}
    result = ai.generate_clinical_reply(clinic(), text, use_ai=False, previous_intent=previous)
    assert result.intent == ClinicIntent.SYMPTOM_TRIAGE


@pytest.mark.parametrize('text', ['evet', 'olur', 'yarın 14'])
def test_context_carry_survives_for_non_medical_turns(text):
    """Düzeltme yalnız daraltma olmalı: tıbbi olmayan kısa cevap akışı sürdürür."""
    result = ai.generate_clinical_reply(clinic(), text, use_ai=False,
                                        previous_intent=ClinicIntent.BOOK_APPOINTMENT)
    assert result.intent == ClinicIntent.BOOK_APPOINTMENT


def _claims_completed_action(reply: str) -> bool:
    result = ai._validated_provider_result(
        {'reply': reply, 'confidence': .9, 'intent': 'book_appointment', 'action': 'collect_info',
         'requires_human_review': False, 'risk_reason': None, 'data': {}},
        deterministic_intent=ClinicIntent.BOOK_APPOINTMENT, deterministic_confidence=.9,
        language='tr', clinic=clinic(), persona=get_persona('selin'))
    return result.risk_reason == 'unverified_model_action_claim'


@pytest.mark.parametrize('reply', [
    'Randevunuz onaylandı.', 'Randevu oluşturuldu.', 'Mesajınız gönderildi.',
    'Your appointment is confirmed.', 'I booked your slot.', 'We have cancelled your booking.',
])
def test_completed_action_claims_are_blocked(reply):
    assert _claims_completed_action(reply)


@pytest.mark.parametrize('reply', [
    'Randevunuz onaylandığında SMS alacaksınız.',
    'Randevu talebinizi ekibimize ilettim, onaylandığında haber verilecek.',
    'Once confirmed by our team, you will receive an SMS.',
    'We have not sent anything yet.',
    'Bu saat uygun mu? Onaylarsanız ekibimiz randevuyu oluşturur.',
])
def test_conditional_and_negated_wording_is_not_an_action_claim(reply):
    """Yanlış pozitif güvenli yönde düşer ama cevabı kalıplaştırıp
    `requires_human_review`'i şişirir — doğrudan operatör-müdahalesi KPI'sına çarpar."""
    assert not _claims_completed_action(reply)


def test_astra_instructions_do_not_pin_a_persona(configured, monkeypatch):
    """`choose_persona` fiyat/sigortayı arzu'ya, semptomu can'a veriyor; sağlayıcı
    talimatı 'You are Selin' derse cevap metni metadata ile çelişiyordu."""
    factory = MagicMock()
    client = factory.return_value.__enter__.return_value
    client.responses.create.return_value = SimpleNamespace(
        status='completed', output_text=json.dumps(payload()), usage=None)
    monkeypatch.setattr('app.ai.astra.OpenAI', factory)
    AstraProvider().generate_chat_reply('Synthetic')
    instructions = client.responses.create.call_args.kwargs['instructions']
    for persona_id in ('selin', 'arzu', 'can'):
        assert get_persona(persona_id).display_name not in instructions
    assert 'persona named in the' in instructions


def test_env_example_matches_provider_default():
    """Örneği kopyalayan kurulum sağlayıcı stratejisini sessizce değiştirmemeli."""
    from pathlib import Path
    env_example = Path(__file__).resolve().parents[2] / '.env.example'
    line = next(l for l in env_example.read_text(encoding='utf-8').splitlines()
                if l.startswith('CLINICAL_LLM_PROVIDER='))
    default = Settings.model_fields['clinical_llm_provider'].default
    assert line.split('=', 1)[1] == default
