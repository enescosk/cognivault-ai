import pytest

from app.models import ClinicIntent
from app.services.clinical_ai_service import (
    analyze_sentiment,
    assess_hallucination_risk,
    derive_consent_signal,
    detect_language,
    extract_clinical_intake,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("merhaba randevu almak istiyorum", "tr"),
        ("yarin musait misiniz", "tr"),
        ("ücret bilgisi alabilir miyim", "tr"),
        ("hello, I need an appointment", "en"),
        ("what is the price", "en"),
        ("do you accept insurance", "en"),
        ("where is the clinic", "en"),
        ("working hours please", "en"),
        ("selam hello", "tr"),
    ],
)
def test_language_detection_matrix(message, expected):
    assert detect_language(message) == expected


@pytest.mark.parametrize(
    ("message", "specialty", "reason"),
    [
        ("Dolgum düştü ve dişim kırıldı", "Restoratif Diş Tedavisi", "restorative_dental"),
        ("Gece dişim zonkluyor kanal olabilir", "Endodonti", "dis_pain_root_canal"),
        ("Diş etim kanıyor", "Periodontoloji", "gum_bleeding"),
        ("Çocuğumun süt dişi ağrıyor", "Pedodonti", "pediatric_dental"),
        ("Şeffaf plak ve ortodonti düşünüyorum", "Ortodonti", "orthodontics"),
        ("İmplant vidası kontrol edilecek", "İmplantoloji", "implant_followup"),
        ("Gömülü yirmilik diş çekimi", "Ağız, Diş ve Çene Cerrahisi", "oral_surgery"),
        ("Gülüş tasarımı ve zirkonyum", "Estetik Diş Hekimliği", "cosmetic_dentistry"),
        ("Cildimde akne ve leke var", "Dermatoloji", "dermatology"),
        ("Botoks ve mezoterapi bilgi", "Medikal Estetik", "medical_aesthetic"),
        ("Genel kontrol olmak istiyorum", "Genel Diş Hekimliği", "general_dental_intake"),
    ],
)
def test_specialty_routing_matrix(message, specialty, reason):
    intake = extract_clinical_intake(message)
    assert intake["specialty"] == specialty
    assert intake["routing_reason"] == reason


@pytest.mark.parametrize(
    ("message", "urgency"),
    [
        ("Genel kontrol istiyorum", "routine"),
        ("Dişim ağrıyor", "priority"),
        ("Yüzüm şişti", "priority"),
        ("Diş etimde kanama var", "priority"),
        ("Nefes alamıyorum", "emergency"),
        ("Kanama durmuyor", "emergency"),
        ("Yutamıyorum", "emergency"),
    ],
)
def test_intake_urgency_boundaries(message, urgency):
    assert extract_clinical_intake(message)["urgency"] == urgency


@pytest.mark.parametrize(
    ("message", "preferred"),
    [
        ("bugün gelebilirim", "bugün"),
        ("yarın uygunum", "yarın"),
        ("pazartesi olsun", "pazartesi"),
        ("çarşamba müsaitim", "carsamba"),
        ("cuma geleyim", "cuma"),
        ("fark etmez", None),
    ],
)
def test_preferred_time_extraction(message, preferred):
    assert extract_clinical_intake(message)["preferred_time"] == preferred


@pytest.mark.parametrize(
    ("message", "direction"),
    [
        ("çok teşekkürler harika oldu", "positive"),
        ("süper, tamam uygundur", "positive"),
        ("rezalet, cevap vermiyorsunuz", "negative"),
        ("çok kötü ve yavaş", "negative"),
        ("randevu istiyorum", "neutral"),
        ("", "neutral"),
    ],
)
def test_sentiment_direction(message, direction):
    score = analyze_sentiment(message)
    assert -1.0 <= score <= 1.0
    if direction == "positive":
        assert score > 0
    elif direction == "negative":
        assert score < 0
    else:
        assert score == 0


@pytest.mark.parametrize(
    ("reply", "slot", "expected_risk"),
    [
        ("Yarın 14:30 uygun.", None, True),
        ("Saat 11 için gelebilirsiniz.", {"status": "full"}, True),
        ("Yarın 10'da bekliyoruz.", {"status": "doctor_review"}, True),
        ("Yarın 14:30 uygun.", {"status": "offered"}, False),
        ("Saat 11 uygun.", {"status": "ok"}, False),
        ("Tercih ettiğiniz aralığı paylaşın.", None, False),
    ],
)
def test_hallucinated_slot_detection(reply, slot, expected_risk):
    risk, reason = assess_hallucination_risk(reply, ClinicIntent.BOOK_APPOINTMENT, slot)
    assert risk is expected_risk
    assert (reason is not None) is expected_risk


def test_hallucinated_slot_rule_only_applies_to_booking():
    risk, reason = assess_hallucination_risk(
        "Fiyat görüşmesi saat 14:30.", ClinicIntent.ASK_PRICE, None
    )
    assert risk is False
    assert reason is None


@pytest.mark.parametrize(
    ("governance", "status", "granted_via"),
    [
        ({"auto_send_allowed": True, "data_residency_mode": "tr_local_first"}, "pending", "notice_only_local_processing"),
        ({"auto_send_allowed": False, "data_residency_mode": "tr_local_first"}, "rejected", "blocked_by_compliance"),
        ({"auto_send_allowed": False}, "rejected", "blocked_by_compliance"),
    ],
)
def test_consent_signal_matrix(governance, status, granted_via):
    signal = derive_consent_signal(governance)
    assert signal["status"] == status
    assert signal["granted_via"] == granted_via
    assert signal["version"] == "v1-explicit-gate"
