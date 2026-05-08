from app.core.config import get_settings


def test_ai_capabilities_requires_auth(client):
    res = client.get("/api/ai/capabilities")
    assert res.status_code == 401


def test_ai_capabilities_reports_offline_fallback(client, customer_token):
    res = client.get("/api/ai/capabilities", headers={"Authorization": f"Bearer {customer_token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["llm"]["offline_capable"] is True
    assert data["llm"]["fallback_engine"] == "local_guided_workflow"
    assert "voice" in data


def test_voice_capabilities_reports_provider_state(client, customer_token):
    res = client.get("/api/voice/capabilities", headers={"Authorization": f"Bearer {customer_token}"})

    assert res.status_code == 200
    data = res.json()
    assert "stt" in data
    assert "tts" in data
    assert "active_provider" in data["stt"]
    assert "active_provider" in data["tts"]


def test_tts_without_configured_provider_returns_503(client, customer_token):
    settings = get_settings()
    original = {
        "openai_api_key": settings.openai_api_key,
        "piper_binary": settings.piper_binary,
        "piper_voice_model": settings.piper_voice_model,
        "speech_tts_provider": settings.speech_tts_provider,
    }
    settings.openai_api_key = ""
    settings.piper_binary = ""
    settings.piper_voice_model = ""
    settings.speech_tts_provider = "auto"
    try:
        res = client.post(
            "/api/voice/synthesize",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"text": "Merhaba"},
        )
    finally:
        for key, value in original.items():
            setattr(settings, key, value)

    assert res.status_code == 503
    assert "Ses sentezi sağlayıcısı hazır değil" in res.json()["error"]["message"]


def test_voice_transcribe_rejects_unsupported_media_type(client, customer_token):
    res = client.post(
        "/api/voice/transcribe",
        headers={"Authorization": f"Bearer {customer_token}"},
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert res.status_code == 415
    assert res.json()["error"]["code"] == "http_error"


def test_streaming_chat_uses_local_fallback_without_llm_runtime(client, customer_token):
    settings = get_settings()
    original = {
        "openai_api_key": settings.openai_api_key,
        "local_llm_base_url": settings.local_llm_base_url,
        "preferred_llm_provider": settings.preferred_llm_provider,
    }
    settings.openai_api_key = ""
    settings.local_llm_base_url = ""
    settings.preferred_llm_provider = "auto"
    try:
        session_res = client.post(
            "/api/chat/sessions",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"title": "Offline stream"},
        )
        session_id = session_res.json()["id"]
        with client.stream(
            "POST",
            f"/api/chat/sessions/{session_id}/messages/stream",
            headers={"Authorization": f"Bearer {customer_token}"},
            json={"content": "I want to book an appointment"},
        ) as res:
            status_code = res.status_code
            body = res.read().decode()
    finally:
        for key, value in original.items():
            setattr(settings, key, value)

    assert status_code == 200
    assert "Happy " in body
    assert "Compliance " in body
    assert '"t": "done"' in body
