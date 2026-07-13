"""
Bildirim servisi — randevu onayı sonrası kullanıcıya e-posta gönderir.
SMTP ayarlanmamışsa konsola/audit log'a yazar (simülasyon modu).
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

ISTANBUL = ZoneInfo("Europe/Istanbul")

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _format_dt(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso_str


def send_appointment_confirmation(
    *,
    to_email: str,
    full_name: str,
    confirmation_code: str,
    department: str,
    scheduled_at: str,
    location: str,
    contact_phone: str,
    purpose: str,
    language: str = "tr",
) -> bool:
    """
    Randevu onay e-postası gönderir.
    SMTP yapılandırılmamışsa log'a yazar ve True döner (simülasyon).
    """
    dt_str = _format_dt(scheduled_at)

    if language == "tr":
        subject = f"Randevunuz Onaylandı — {confirmation_code}"
        body = f"""Merhaba {full_name},

Randevunuz başarıyla oluşturuldu. Detaylar aşağıdadır:

  📋 Onay Kodu   : {confirmation_code}
  🏢 Departman   : {department}
  📅 Tarih & Saat: {dt_str}
  📍 Konum       : {location}
  📞 İletişim    : {contact_phone}
  💬 Amaç        : {purpose}

Randevunuzu iptal etmek veya değiştirmek için destek ekibimizle iletişime geçebilirsiniz.

Cognivault — Kurumsal İş Akışı Platformu
"""
    else:
        subject = f"Appointment Confirmed — {confirmation_code}"
        body = f"""Hello {full_name},

Your appointment has been successfully created. Details below:

  📋 Confirmation Code : {confirmation_code}
  🏢 Department        : {department}
  📅 Date & Time       : {dt_str}
  📍 Location          : {location}
  📞 Contact Phone     : {contact_phone}
  💬 Purpose           : {purpose}

To cancel or reschedule, please reach out to our support team.

Cognivault — Enterprise Workflow Platform
"""

    smtp_host = getattr(settings, "smtp_host", "")
    smtp_user = getattr(settings, "smtp_user", "")
    smtp_pass = getattr(settings, "smtp_pass", "")
    smtp_port = int(getattr(settings, "smtp_port", 587))
    from_email = getattr(settings, "smtp_from", smtp_user or "noreply@cognivault.local")

    if not smtp_host or not smtp_user:
        # Simülasyon modu — gerçek mail yok ama log'a yaz
        logger.info(
            "📧 [SIM] Randevu bildirimi → %s | %s | %s | %s",
            to_email, confirmation_code, department, dt_str,
        )
        print(f"\n{'='*60}")
        print(f"📧 RANDEVU BİLDİRİMİ (SİMÜLASYON)")
        print(f"   Alıcı : {to_email}")
        print(f"   Konu  : {subject}")
        print(body)
        print("="*60)
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_email
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())

        logger.info("📧 Randevu bildirimi gönderildi → %s (%s)", to_email, confirmation_code)
        return True
    except Exception as exc:
        logger.warning("📧 Mail gönderilemedi: %s", exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SMS notifications — patient page randevu akışı için
# ─────────────────────────────────────────────────────────────────────────────
#
# MVP: SMS sağlayıcı entegre edilmedi; mesajlar log'a + audit'e yazılır.
# L2 fazında Netgsm/Verimor/Turkcell adapter buraya eklenecek.
#
# Tasarım kararı: iki ayrı fonksiyon (patient + doctor) çünkü:
#   • Şablon farklı (hastaya kibar onay; doktora kısa özet + hasta adı)
#   • Doktor numarası klinik tarafından konfigüre edilir, hastaya görünmez
#   • Audit log'da iki ayrı kanal — denetlenebilirlik için kritik


def _format_dt_tr(dt: datetime) -> str:
    """TR zaman formatı: '28 Mayıs Çarşamba, 14:30' — daima İstanbul saatiyle.

    DB'den gelen naive datetime UTC'dir; SMS'e olduğu gibi yazılırsa hasta
    randevusunu 3 saat erken görür. Naive → UTC varsay, sonra İstanbul'a çevir.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(ISTANBUL)
    months = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık",
    }
    weekdays = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
        4: "Cuma", 5: "Cumartesi", 6: "Pazar",
    }
    return f"{dt.day} {months[dt.month]} {weekdays[dt.weekday()]}, {dt.strftime('%H:%M')}"


def send_appointment_sms_to_patient(
    *,
    patient_phone: str,
    patient_name: str | None,
    clinic_name: str,
    clinic_phone: str | None,
    department: str,
    physician_name: str | None,
    starts_at: datetime,
    confirmation_code: str | None = None,
) -> bool:
    """Hastaya randevu onay SMS'i.

    Mock mode (varsayılan): konsola + log'a yazar, audit izi düşer.
    Gerçek sağlayıcı eklendiğinde bu fonksiyonun gövdesi değişir, imza sabit kalır.
    """
    name = patient_name or "Sayın Hastamız"
    dr = f" Dr. {physician_name} ile" if physician_name else ""
    when = _format_dt_tr(starts_at)
    code = f" Kod: {confirmation_code}." if confirmation_code else ""
    contact = f" Sorularınız için: {clinic_phone}" if clinic_phone else ""

    body = (
        f"Sayın {name}, {clinic_name} {department} randevunuz{dr} "
        f"{when} olarak oluşturuldu.{code}{contact}"
    )

    from app.services.sms_service import get_sms_provider

    result = get_sms_provider().send(to=patient_phone, body=body)
    logger.info(
        "📱 [SMS-PATIENT] → %s · provider=%s ok=%s · %s",
        patient_phone, result.provider, result.ok, body,
    )
    return result.ok


def send_appointment_sms_to_doctor(
    *,
    doctor_phone: str | None,
    doctor_name: str | None,
    clinic_name: str,
    patient_name: str | None,
    patient_phone: str,
    department: str,
    starts_at: datetime,
    patient_complaint_summary: str | None = None,
) -> bool:
    """Doktora (veya klinik genel hattına) yeni randevu uyarısı.

    `doctor_phone` None ise klinik admin telefonuna düşmesi için fallback
    çağıran tarafça yapılır. Burada None gelirse SMS atılmaz, log'a düşer.
    """
    if not doctor_phone:
        logger.warning(
            "📱 [SMS-DOCTOR] Doktor telefonu yok — bildirim atlandı | clinic=%s patient=%s",
            clinic_name, patient_name or "anonim"
        )
        return False

    name = doctor_name or "Doktorum"
    pt = patient_name or "Anonim Hasta"
    when = _format_dt_tr(starts_at)
    complaint = f" Şikayet özeti: {patient_complaint_summary}" if patient_complaint_summary else ""

    body = (
        f"Sayın {name}, yeni randevu: {pt} ({patient_phone}) "
        f"{department}, {when}.{complaint}"
    )

    from app.services.sms_service import get_sms_provider

    result = get_sms_provider().send(to=doctor_phone, body=body)
    logger.info(
        "📱 [SMS-DOCTOR] → %s · provider=%s ok=%s · %s",
        doctor_phone, result.provider, result.ok, body,
    )
    return result.ok
