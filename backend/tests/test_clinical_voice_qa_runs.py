from __future__ import annotations

from app.models import ClinicalVoiceQARun
from app.services.clinical_service import ensure_default_clinic


def test_operator_can_record_and_list_real_device_voice_qa(client, db_session, operator_token):
    clinic = ensure_default_clinic(db_session)
    auth = {"Authorization": f"Bearer {operator_token}"}

    empty = client.get("/api/clinical/voice-qa-runs", headers=auth)
    assert empty.status_code == 200, empty.text
    assert empty.json()["summary"]["total_runs"] == 0
    assert empty.json()["summary"]["ready_for_pilot"] is False

    created = client.post(
        "/api/clinical/voice-qa-runs",
        headers=auth,
        json={
            "tester": "QA Ayse",
            "device": "iPhone 15",
            "browser": "Safari",
            "audio_condition": "Quiet room",
            "voice_mode": "local",
            "scenario": "core",
            "mic_permission_seconds": 1.2,
            "first_assistant_audio_seconds": 2.8,
            "transcript_correct": True,
            "transcript_shown": True,
            "retry_count": 0,
            "completed_under_60s": True,
            "appointment_created": True,
            "operator_intervention": False,
            "severity": "pass",
            "notes": "Normal akış sorunsuz tamamlandı.",
        },
    )
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload["clinic_id"] == clinic.id
    assert payload["appointment_created"] is True

    stored = db_session.get(ClinicalVoiceQARun, payload["id"])
    assert stored is not None
    assert stored.device == "iPhone 15"

    listing = client.get("/api/clinical/voice-qa-runs", headers=auth)
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["summary"]["total_runs"] == 1
    assert data["summary"]["appointment_success_rate"] == 100
    assert data["summary"]["under_60_rate"] == 100
    assert data["summary"]["transcript_correct_rate"] == 100
    assert data["runs"][0]["id"] == payload["id"]


def test_real_device_qa_runs_feed_pilot_gate(client, db_session, operator_token):
    clinic = ensure_default_clinic(db_session)
    for idx in range(12):
        db_session.add(
            ClinicalVoiceQARun(
                clinic_id=clinic.id,
                tester=f"QA {idx}",
                device="Android",
                browser="Chrome",
                audio_condition="Reception noise",
                voice_mode="local",
                scenario="core",
                transcript_correct=True,
                transcript_shown=True,
                retry_count=0,
                completed_under_60s=True,
                appointment_created=True,
                operator_intervention=False,
                severity="pass",
                metadata_json={},
            )
        )
    db_session.commit()

    metrics = client.get(
        "/api/clinical/pilot-metrics",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert metrics.status_code == 200, metrics.text
    by_id = {item["id"]: item for item in metrics.json()["metrics"]}
    assert by_id["real_device_qa_runs"]["value"] == 12
    assert by_id["real_device_qa_runs"]["passed"] is True


def test_pilot_weekly_report_is_copyable_markdown(client, db_session, operator_token):
    ensure_default_clinic(db_session)
    report = client.get(
        "/api/clinical/pilot-weekly-report?days=7",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert report.status_code == 200, report.text
    payload = report.json()
    assert payload["window_days"] == 7
    assert payload["summary"]["clinic_name"]
    markdown = payload["markdown"]
    assert markdown.startswith("# ")
    assert "## Totals" in markdown
    assert "Voice attempts" in markdown
    assert "## KPIs" in markdown
    assert "## Next Actions" in markdown


def test_pilot_launch_checklist_exposes_rollback_and_incident_path(client, db_session, operator_token):
    ensure_default_clinic(db_session)
    checklist = client.get(
        "/api/clinical/pilot-launch-checklist?days=7",
        headers={"Authorization": f"Bearer {operator_token}"},
    )
    assert checklist.status_code == 200, checklist.text
    payload = checklist.json()
    assert payload["window_days"] == 7
    assert isinstance(payload["ready_for_launch"], bool)
    assert any(item["id"] == "emergency_safety" for item in payload["checklist"])
    assert any("Switch clinic voice settings" in item for item in payload["rollback_plan"])
    assert any("Severity 1" in item for item in payload["incident_response"])
