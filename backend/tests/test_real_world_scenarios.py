from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from app.ai.runtime import select_llm_runtime
from app.agent.orchestrator import parse_department, parse_preferred_date
from app.core.config import get_settings
from app.models import Appointment, AppointmentSlot, Department, Organization, RoutingRule


def _force_offline_ai():
    settings = get_settings()
    original = {
        "openai_api_key": settings.openai_api_key,
        "local_llm_base_url": settings.local_llm_base_url,
        "preferred_llm_provider": settings.preferred_llm_provider,
    }
    settings.openai_api_key = ""
    settings.local_llm_base_url = ""
    settings.preferred_llm_provider = "auto"
    return settings, original


def _restore_settings(settings, original: dict) -> None:
    for key, value in original.items():
        setattr(settings, key, value)


def _seed_technical_slots(db_session) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for index in range(3):
        start = now + timedelta(days=1, hours=10 + index)
        db_session.add(
            AppointmentSlot(
                department="Technical Support",
                start_time=start,
                end_time=start + timedelta(minutes=30),
                location="Remote",
            )
        )
    db_session.commit()


def _seed_enterprise_routing(db_session) -> None:
    organization = Organization(name="Scenario Corp", domain="scenario.local")
    db_session.add(organization)
    db_session.flush()

    technical = Department(
        organization_id=organization.id,
        name="Technical Support",
        description="Production incidents and connectivity issues.",
    )
    general = Department(
        organization_id=organization.id,
        name="General Support",
        description="Fallback queue.",
    )
    db_session.add_all([technical, general])
    db_session.flush()
    db_session.add(
        RoutingRule(
            organization_id=organization.id,
            intent="technical_issue",
            department_id=technical.id,
            keywords=["internet", "calismiyor", "baglanamiyorum", "vpn", "sistem", "hata"],
            confidence_boost=78,
        )
    )
    db_session.commit()


def test_noisy_turkish_appointment_flow_completes_offline(client, customer_token, db_session):
    _seed_technical_slots(db_session)
    settings, original = _force_offline_ai()
    try:
        session_res = client.post(
            "/api/chat/sessions",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"title": "Gercek hayat destek"},
        )
        assert session_res.status_code == 200
        session_id = session_res.json()["id"]

        first = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"content": "slm, tekink destk icin randevu alcam yarin 0532 111 22 33"},
        )
        assert first.status_code == 200
        assert "Kısa bir amaç" in first.json()["assistant_reply"]["message"]

        second = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"content": "VPN baglantim surekli kopuyor, SAP toplantisindan once cozulmeli"},
        )
        assert second.status_code == 200
        assert "Uygun slotları buldum" in second.json()["assistant_reply"]["message"]

        final = client.post(
            f"/api/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"content": "1"},
        )
        assert final.status_code == 200
        reply = final.json()["assistant_reply"]
        assert reply["outcome"] == "completed"
        assert reply["confirmation_card"]["department"] == "Technical Support"
        assert db_session.query(Appointment).count() == 1
    finally:
        _restore_settings(settings, original)


def test_real_world_text_understanding_handles_typos_and_ascii_turkish():
    assert parse_department("tekink destk lazim vpn calismio") == "Technical Support"
    assert parse_department("ftrmda yanlis ucret var odeme yapamiyorum") == "Billing Operations"
    assert parse_department("kvk/gdpr sozlesme denetimi icin gorusme") == "Compliance Advisory"
    assert parse_preferred_date("yarin ogleden sonra musaitseniz") is not None


def test_enterprise_escalates_noisy_connectivity_complaint(client, operator_token, db_session):
    _seed_enterprise_routing(db_session)
    session_res = client.post(
        "/api/enterprise/sessions",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "customer_name": "Gercek Musteri",
            "customer_email": "musteri@example.com",
            "customer_phone": "+90 532 222 33 44",
            "channel": "phone",
        },
    )
    assert session_res.status_code == 200
    session_id = session_res.json()["id"]

    message_res = client.post(
        f"/api/enterprise/sessions/{session_id}/messages",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"content": "internet calismio, vpn baglanmiyo acil insan temsilci istiyorum"},
    )

    assert message_res.status_code == 200
    decision = message_res.json()["decision"]
    assert decision["intent"] == "technical_issue"
    assert decision["action"] == "escalate"
    assert decision["department"]["name"] == "Technical Support"
    assert decision["ticket"]["priority"] == "high"


def test_local_voice_providers_are_exercised_through_api(client, customer_token, tmp_path):
    whisper_bin = tmp_path / "fake_whisper.py"
    whisper_model = tmp_path / "fake-whisper.bin"
    piper_bin = tmp_path / "fake_piper.py"
    piper_model = tmp_path / "fake-piper.onnx"
    whisper_model.write_text("model", encoding="utf-8")
    piper_model.write_text("model", encoding="utf-8")

    whisper_bin.write_text(
        """#!/usr/bin/env python3
import sys
out = sys.argv[sys.argv.index('-of') + 1]
open(out + '.txt', 'w', encoding='utf-8').write('Teknik destek icin randevu almak istiyorum')
""",
        encoding="utf-8",
    )
    piper_bin.write_text(
        """#!/usr/bin/env python3
import sys, wave
out = sys.argv[sys.argv.index('--output_file') + 1]
with wave.open(out, 'wb') as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(16000)
    wav.writeframes(b'\\x00\\x00' * 1600)
""",
        encoding="utf-8",
    )
    os.chmod(whisper_bin, 0o755)
    os.chmod(piper_bin, 0o755)

    settings = get_settings()
    original = {
        "openai_api_key": settings.openai_api_key,
        "speech_stt_provider": settings.speech_stt_provider,
        "speech_tts_provider": settings.speech_tts_provider,
        "whisper_cpp_binary": settings.whisper_cpp_binary,
        "whisper_cpp_model": settings.whisper_cpp_model,
        "piper_binary": settings.piper_binary,
        "piper_voice_model": settings.piper_voice_model,
    }
    settings.openai_api_key = ""
    settings.speech_stt_provider = "local"
    settings.speech_tts_provider = "local"
    settings.whisper_cpp_binary = str(whisper_bin)
    settings.whisper_cpp_model = str(whisper_model)
    settings.piper_binary = str(piper_bin)
    settings.piper_voice_model = str(piper_model)
    try:
        stt = client.post(
            "/api/voice/transcribe",
            headers={"Authorization": f"Bearer {customer_token}"},
            files={"file": ("sample.webm", b"not-real-audio-but-provider-is-faked", "audio/webm")},
        )
        tts = client.post(
            "/api/voice/synthesize",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"text": "Merhaba, talebinizi aldım."},
        )
        capabilities = client.get("/api/ai/capabilities", headers={"Authorization": f"Bearer {customer_token}"})
    finally:
        _restore_settings(settings, original)

    assert stt.status_code == 200
    assert stt.json()["provider"] == "whisper_cpp"
    assert "Teknik destek" in stt.json()["text"]
    assert tts.status_code == 200
    assert tts.headers["X-Cognivault-Voice-Provider"] == "piper"
    assert tts.content.startswith(b"RIFF")
    assert capabilities.status_code == 200


def test_local_llm_runtime_is_selected_when_configured():
    settings = get_settings()
    original = {
        "openai_api_key": settings.openai_api_key,
        "local_llm_base_url": settings.local_llm_base_url,
        "local_llm_model": settings.local_llm_model,
        "preferred_llm_provider": settings.preferred_llm_provider,
    }
    settings.openai_api_key = ""
    settings.local_llm_base_url = "http://localhost:8080/v1"
    settings.local_llm_model = "cognivault-scenario-model"
    settings.preferred_llm_provider = "local"
    try:
        runtime = select_llm_runtime()
    finally:
        _restore_settings(settings, original)

    assert runtime is not None
    assert runtime.provider == "local_openai_compatible"
    assert runtime.model == "cognivault-scenario-model"
