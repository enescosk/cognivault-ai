"""SMS sağlayıcı katmanı — seçim, Netgsm gönderimi, asla-raise-etmeme sözleşmesi."""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import sms_service
from app.services.sms_service import (
    MockSmsProvider,
    NetgsmSmsProvider,
    get_sms_provider,
    netgsm_number,
    sms_capabilities,
)


@pytest.fixture()
def settings():
    s = get_settings()
    original = (s.sms_provider, s.netgsm_usercode, s.netgsm_password, s.netgsm_msgheader)
    yield s
    (s.sms_provider, s.netgsm_usercode, s.netgsm_password, s.netgsm_msgheader) = original


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = str(self._payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


# ─── Numara normalizasyonu ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+90 532 111 22 33", "5321112233"),
        ("+905321112233", "5321112233"),
        ("05321112233", "5321112233"),
        ("905321112233", "5321112233"),
        ("532 111 22 33", "5321112233"),
    ],
)
def test_netgsm_number_normalization(raw, expected):
    assert netgsm_number(raw) == expected


# ─── Sağlayıcı seçimi ────────────────────────────────────────────────────────

def test_default_provider_is_mock(settings):
    settings.sms_provider = "mock"
    assert isinstance(get_sms_provider(), MockSmsProvider)


def test_netgsm_selected_with_credentials(settings):
    settings.sms_provider = "netgsm"
    settings.netgsm_usercode = "8501234567"
    settings.netgsm_password = "secret"
    settings.netgsm_msgheader = "DEMOKLINIK"
    assert isinstance(get_sms_provider(), NetgsmSmsProvider)


def test_netgsm_without_credentials_falls_back_to_mock_loudly(settings, caplog):
    settings.sms_provider = "netgsm"
    settings.netgsm_usercode = ""
    settings.netgsm_password = ""
    settings.netgsm_msgheader = ""
    with caplog.at_level("ERROR"):
        provider = get_sms_provider()
    assert isinstance(provider, MockSmsProvider)
    assert any("GERÇEK SMS" in r.message for r in caplog.records)


def test_capabilities_reports_misconfiguration(settings):
    settings.sms_provider = "netgsm"
    settings.netgsm_usercode = ""
    caps = sms_capabilities()
    assert caps["misconfigured"] is True
    assert caps["active_provider"] == "mock"
    assert caps["real_delivery"] is False


# ─── Netgsm gönderimi ────────────────────────────────────────────────────────

def _configure_netgsm(settings):
    settings.sms_provider = "netgsm"
    settings.netgsm_usercode = "8501234567"
    settings.netgsm_password = "secret"
    settings.netgsm_msgheader = "DEMOKLINIK"


def test_netgsm_send_success(settings, monkeypatch):
    _configure_netgsm(settings)
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]
        captured["auth"] = kwargs["auth"]
        return _FakeResponse(200, {"code": "00", "jobid": "1234567"})

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    result = NetgsmSmsProvider().send(to="+905321112233", body="Randevunuz oluşturuldu.")
    assert result.ok is True
    assert result.message_id == "1234567"
    assert captured["json"]["messages"][0]["no"] == "5321112233"
    assert captured["json"]["msgheader"] == "DEMOKLINIK"
    assert captured["auth"] == ("8501234567", "secret")


def test_netgsm_send_rejected_code(settings, monkeypatch):
    _configure_netgsm(settings)
    import httpx

    monkeypatch.setattr(httpx, "post", lambda url, **kw: _FakeResponse(200, {"code": "30"}))
    result = NetgsmSmsProvider().send(to="+905321112233", body="test")
    assert result.ok is False
    assert "netgsm_code:30" == result.error


def test_netgsm_send_network_error_never_raises(settings, monkeypatch):
    _configure_netgsm(settings)
    import httpx

    def boom(url, **kw):
        raise httpx.ConnectError("bağlantı yok")

    monkeypatch.setattr(httpx, "post", boom)
    result = NetgsmSmsProvider().send(to="+905321112233", body="test")
    assert result.ok is False
    assert "bağlantı yok" in (result.error or "")


def test_netgsm_rejects_invalid_number_without_http(settings, monkeypatch):
    _configure_netgsm(settings)
    import httpx

    def should_not_be_called(url, **kw):  # pragma: no cover
        raise AssertionError("geçersiz numara için HTTP çağrısı yapılmamalı")

    monkeypatch.setattr(httpx, "post", should_not_be_called)
    result = NetgsmSmsProvider().send(to="12345", body="test")
    assert result.ok is False
    assert result.error and result.error.startswith("invalid_number")


# ─── notification_service entegrasyonu ───────────────────────────────────────

def test_patient_sms_uses_active_provider(settings, monkeypatch):
    sent: list[tuple[str, str]] = []

    class _Spy(MockSmsProvider):
        def send(self, *, to: str, body: str):
            sent.append((to, body))
            return super().send(to=to, body=body)

    monkeypatch.setattr(sms_service, "get_sms_provider", lambda: _Spy())
    from datetime import datetime, timezone

    from app.services.notification_service import send_appointment_sms_to_patient

    ok = send_appointment_sms_to_patient(
        patient_phone="+905321112233",
        patient_name="Elif Kaya",
        clinic_name="Demo Klinik",
        clinic_phone="+902120000000",
        department="Endodonti",
        physician_name="Ece Arslan",
        starts_at=datetime(2026, 7, 15, 7, 20, tzinfo=timezone.utc),
        confirmation_code="CV000123",
    )
    assert ok is True
    assert len(sent) == 1
    to, body = sent[0]
    assert to == "+905321112233"
    # Saat İstanbul'a çevrilmiş olmalı (07:20 UTC → 10:20 TR)
    assert "10:20" in body
    assert "Elif Kaya" in body and "Endodonti" in body
