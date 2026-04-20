"""
Bildirim servisi — randevu onayı sonrası kullanıcıya e-posta gönderir.
SMTP ayarlanmamışsa konsola/audit log'a yazar (simülasyon modu).
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
