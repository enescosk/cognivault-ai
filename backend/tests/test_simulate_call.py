"""`app.ops.simulate_call` sözleşme testleri.

Araç gerçek bir backend'e HTTP atmak için var; burada HTTP katmanı TestClient'a
yönlendirilerek ORKESTRASYONU test edilir: turlar aynı CallSid ile mi gidiyor,
TwiML doğru okunuyor mu, kapı kararları doğru mu, çağrı doğru yerde kapanıyor mu.

Ayrıca imza üreticisi doğrulayıcıya karşı çapraz test edilir — araç Twilio'yu
taklit ettiğini iddia ediyor, bu iddianın kanıtı burada.
"""
import pytest

from app.core.webhook_security import verify_twilio_signature
from app.models import ClinicChannel
from app.ops import simulate_call as sim
from app.ops.bind_channel import bind_channel
from app.services.clinical_service import ensure_default_clinic

BASE = "http://testserver"


@pytest.fixture
def routed(client, monkeypatch):
    """post_form/fetch_audio'yu TestClient'a bağla — gerçek soket yok."""
    def post_form(base_url, path, params, auth_token, timeout=30.0):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if auth_token:
            headers["X-Twilio-Signature"] = sim.twilio_signature(
                auth_token, base_url.rstrip("/") + path, params)
        response = client.post(path, data=params, headers=headers)
        return response.status_code, response.text

    def fetch_audio(base_url, path, timeout=30.0):
        response = client.get(path)
        return len(response.content) if response.status_code == 200 else None

    monkeypatch.setattr(sim, "post_form", post_form)
    monkeypatch.setattr(sim, "fetch_audio", fetch_audio)
    return client


def run(name, *, to_number, token=""):
    return sim.run_scenario(name, sim.SCENARIOS[name], base_url=BASE, to_number=to_number,
                            from_number="+905557009911", auth_token=token)


@pytest.fixture
def bound_number(db_session):
    clinic = ensure_default_clinic(db_session)
    number = "+903120009911"
    assert bind_channel(db_session, clinic_slug=clinic.slug, phone=number,
                        channel=ClinicChannel.PHONE, deactivate=False) == 0
    return number


def test_signature_generator_matches_server_verifier():
    """Üretici ile doğrulayıcı bağımsız iki uygulama; aynı sonuca varmalılar.

    Bu eşleşme bozulursa araç sessizce 401 yer ve 'telefon akışı çalışmıyor'
    sanılır — oysa kırık olan simülatörün imzasıdır.
    """
    url = f"{BASE}/api/webhooks/voice/gather"
    params = {"CallSid": "CA1", "From": "+905550000000", "SpeechResult": "merhaba", "To": "+90312"}
    signature = sim.twilio_signature("secret-token", url, params)
    assert verify_twilio_signature(auth_token="secret-token", request_url=url,
                                   form_params=params, signature_header=signature)
    assert not verify_twilio_signature(auth_token="baska-token", request_url=url,
                                       form_params=params, signature_header=signature)


def test_unbound_number_is_rejected_when_strict_binding_is_on(routed, db_session, monkeypatch):
    """Multi-tenant güvenliği: bağlanmamış numara veri yazmadan kapanmalı."""
    from sqlalchemy import select
    from app.core.config import get_settings
    from app.models import ClinicConversation

    monkeypatch.setattr(get_settings(), "clinical_channel_binding_strict", True)
    result = run("baglanmamis-numara", to_number="+903129999123")
    assert result.passed, result.checks
    assert not result.turns[-1].has_gather
    assert db_session.scalars(select(ClinicConversation).where(
        ClinicConversation.external_thread_id == result.call_sid)).first() is None


def test_unbound_check_is_reported_as_unmeasured_when_strict_is_off(routed, monkeypatch):
    """Strict kapalıyken çağrı varsayılan kliniğe düşer — bu kapı ölçülemez.

    Yeşil raporlamak F1.4'ü yalan kanıtlar; kırmızı raporlamak aracı varsayılan
    kurulumda kullanılmaz yapar. Üçüncü durum tek dürüst seçenek.
    """
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "clinical_channel_binding_strict", False)
    result = run("baglanmamis-numara", to_number="+903129999124")
    labels = {label: ok for label, ok, _ in result.checks}
    assert labels["Bağlanmamış numara reddedildi"] is None
    assert result.passed  # ölçülemeyen kapı paketi kırmızıya çevirmez
    reason = next(d for l, _, d in result.checks if l == "Bağlanmamış numara reddedildi")
    assert "STRICT" in reason and "F1.4" in reason


def test_emergency_turn_overrides_booking_flow(routed, bound_number):
    result = run("acil", to_number=bound_number)
    assert result.passed, result.checks
    joined = " ".join(t.raw for t in result.turns).lower()
    assert "112" in joined or "doktor ekranına" in joined


def test_unintelligible_speech_keeps_the_call_alive(routed, bound_number):
    """Boş STT çıktısı çağrıyı düşürmemeli — hasta tekrar deneyebilmeli."""
    result = run("anlasilmadi", to_number=bound_number)
    assert result.passed, result.checks
    assert result.turns[-1].has_gather


def test_every_turn_reuses_one_call_sid(routed, bound_number):
    """Turlar farklı CallSid'le giderse görüşme parçalanır ve bağlam kaybolur."""
    sent = []
    original = sim.post_form
    sim_post = lambda *a, **k: (sent.append(a[2]), original(*a, **k))[1]
    try:
        sim.post_form = sim_post
        result = run("acil", to_number=bound_number)
    finally:
        sim.post_form = original
    sids = {params["CallSid"] for params in sent}
    assert sids == {result.call_sid}


def test_scenario_catalog_is_self_describing():
    """--list çıktısı senaryo eklendiğinde kendiliğinden güncellensin."""
    for name, spec in sim.SCENARIOS.items():
        assert spec["why"].endswith("?"), name
        assert isinstance(spec["says"], list) and spec["says"], name


def test_twiml_parser_reads_play_say_and_gather(routed):
    play = '<Response><Gather><Play>/api/webhooks/voice/tts/abc.wav</Play></Gather></Response>'
    spoken, _, has_gather = sim.parse_twiml(BASE, play)
    assert spoken.startswith("[ses] /api/webhooks/voice/tts/abc.wav") and has_gather

    say = '<Response><Say language="tr-TR">Merhaba</Say></Response>'
    spoken, audio, has_gather = sim.parse_twiml(BASE, say)
    assert spoken == "Merhaba" and audio is None and not has_gather
