import pytest


def test_branding_endpoints(client, admin_token, operator_token):
    # GET branding as admin
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/clinic/admin/branding", headers=headers)
    assert res.status_code == 200
    assert "branding" in res.json()

    # PATCH branding as admin
    res = client.patch(
        "/api/clinic/admin/branding",
        headers=headers,
        json={
            "headline": "Yeni Diş Kliniği",
            "sub_headline": "Yeni estetik servislerimizle",
            "primary_color": "#ff0000",
        }
    )
    assert res.status_code == 200
    assert res.json()["branding"]["headline"] == "Yeni Diş Kliniği"
    assert res.json()["branding"]["primary_color"] == "#ff0000"

    # Unauthorized access as operator
    op_headers = {"Authorization": f"Bearer {operator_token}"}
    res = client.get("/api/clinic/admin/branding", headers=op_headers)
    assert res.status_code == 403


def test_voice_settings_endpoints_are_admin_only_and_diagnostic(client, admin_token, operator_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    initial = client.get("/api/clinic/admin/voice-settings", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["settings"]["stt_provider"] == "local"
    assert "credentials" in initial.json()

    updated = client.patch(
        "/api/clinic/admin/voice-settings",
        headers=headers,
        json={
            "stt_provider": "elevenlabs",
            "tts_provider": "elevenlabs",
            "external_enabled": True,
            "allow_cross_border_processors": True,
            "tts_voice": "voice-1",
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["settings"]["stt_provider"] == "elevenlabs"
    assert payload["settings"]["allow_cross_border_processors"] is True
    assert payload["simulated_full_consent"]["external_transfer_allowed"] is True

    diagnostic = client.post("/api/clinic/admin/voice-settings/test", headers=headers)
    assert diagnostic.status_code == 200
    assert diagnostic.json()["settings"]["tts_provider"] == "elevenlabs"

    op_headers = {"Authorization": f"Bearer {operator_token}"}
    forbidden = client.get("/api/clinic/admin/voice-settings", headers=op_headers)
    assert forbidden.status_code == 403


def test_public_voice_uses_clinic_voice_provider_override(client, db_session, admin_token, monkeypatch):
    from app.api.routes import public as public_routes
    from app.services.clinical_service import ensure_default_clinic

    clinic = ensure_default_clinic(db_session)
    clinic.settings_json = {
        **(clinic.settings_json or {}),
        "allow_cross_border_processors": True,
        "voice": {
            "stt_provider": "elevenlabs",
            "tts_provider": "elevenlabs",
            "external_enabled": True,
        },
    }
    db_session.add(clinic)
    db_session.commit()

    disclosure = client.get(f"/api/public/clinics/{clinic.slug}/disclosure").json()
    consent = client.post(
        f"/api/public/clinics/{clinic.slug}/consent",
        json={
            "disclosure_version": disclosure["version"],
            "disclosure_hash": disclosure["body_hash"],
            "accepted_cross_border": True,
            "accepted_voice_processing": True,
        },
    ).json()
    session = client.post(
        f"/api/public/clinics/{clinic.slug}/conversations",
        headers={"Authorization": f"Bearer {consent['consent_token']}"},
        json={"full_name": "Voice Test", "phone": "+90 555 111 44 55"},
    ).json()

    captured: list[dict] = []

    class _FakeTTS:
        def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
            return b"RIFFfake-wave", "audio/wav"

    def fake_get_tts_provider(external_transfer_allowed=False, *, consent_granted=False, **kwargs):
        captured.append(
            {
                "external_transfer_allowed": external_transfer_allowed,
                "consent_granted": consent_granted,
                **kwargs,
            }
        )
        return _FakeTTS()

    monkeypatch.setattr(public_routes, "get_tts_provider", fake_get_tts_provider)
    res = client.post(
        f"/api/public/clinics/{clinic.slug}/voice/synthesize",
        headers={"Authorization": f"Bearer {session['session_token']}"},
        json={"text": "Merhaba", "voice": "nova"},
    )
    assert res.status_code == 200, res.text
    assert captured == [
        {
            "external_transfer_allowed": True,
            "consent_granted": True,
            "provider_name": "elevenlabs",
            "external_enabled": True,
        }
    ]


def test_doctors_crud_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a doctor
    res = client.post(
        "/api/clinic/admin/doctors",
        headers=headers,
        json={"full_name": "Dr. Ahmet Yılmaz", "specialty": "Ortodonti", "is_active": True}
    )
    assert res.status_code == 200
    doctor_id = res.json()["id"]
    assert res.json()["full_name"] == "Dr. Ahmet Yılmaz"

    # 2. Get list of doctors
    res = client.get("/api/clinic/admin/doctors", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(doc["id"] == doctor_id for doc in res.json())

    # 3. Update the doctor
    res = client.patch(
        f"/api/clinic/admin/doctors/{doctor_id}",
        headers=headers,
        json={"full_name": "Dr. Ahmet Yılmaz Edit", "specialty": "Ortodonti Edit", "is_active": False}
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Dr. Ahmet Yılmaz Edit"
    assert not res.json()["is_active"]

    # 4. Delete the doctor
    res = client.delete(f"/api/clinic/admin/doctors/{doctor_id}", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # 5. Delete again should return 404
    res = client.delete(f"/api/clinic/admin/doctors/{doctor_id}", headers=headers)
    assert res.status_code == 404


def test_services_crud_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a service
    res = client.post(
        "/api/clinic/admin/services",
        headers=headers,
        json={"name": "Kanal Tedavisi", "description": "Detaylı endodonti hizmeti", "is_active": True}
    )
    assert res.status_code == 200
    service_id = res.json()["id"]
    assert res.json()["name"] == "Kanal Tedavisi"

    # 2. Get list
    res = client.get("/api/clinic/admin/services", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Update
    res = client.patch(
        f"/api/clinic/admin/services/{service_id}",
        headers=headers,
        json={"name": "Kanal Tedavisi Edit", "description": "Yeni açıklama", "is_active": True}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Kanal Tedavisi Edit"

    # 4. Delete
    res = client.delete(f"/api/clinic/admin/services/{service_id}", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_kvkk_disclosures_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a KVKK disclosure version
    res = client.post(
        "/api/clinic/admin/disclosures",
        headers=headers,
        json={"version": "v1.0.1", "disclosure_text": "Kişisel verilerin korunması kanunu aydınlatma metni...", "is_active": True}
    )
    assert res.status_code == 200
    disclosure_id = res.json()["id"]
    assert res.json()["version"] == "v1.0.1"

    # 2. Get disclosures list
    res = client.get("/api/clinic/admin/disclosures", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert res.json()[0]["id"] == disclosure_id
