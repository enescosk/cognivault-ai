"""SMS sağlayıcı soyutlaması — randevu onayları için GERÇEK gönderim yolu.

Bugüne kadar tüm SMS'ler konsola yazılan simülasyondu; pilot klinikte hasta
"onay SMS'i gönderildi" duyup hiçbir mesaj almayacaktı. Bu modül gönderimi
sağlayıcı arkasına alır:

- MockSmsProvider  — varsayılan; log + konsol (demo/dev davranışı korunur).
- NetgsmSmsProvider — Netgsm REST v2 (yurt içi sağlayıcı; randevu onayı
  "bilgilendirme" kategorisindedir, ticari ileti/İYS onayı gerektirmez;
  msgheader yine de operatör onaylı başlık olmalıdır).

Sözleşme: `send()` ASLA exception yükseltmez — SMS altyapısındaki bir arıza
randevu oluşturmayı geri alamaz/bozamaz. Başarısızlık `SmsResult.ok=False`
ile döner ve loglanır; çağıran akış devam eder.
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmsResult:
    ok: bool
    provider: str
    message_id: str | None = None
    error: str | None = None


def netgsm_number(phone: str) -> str:
    """Telefonu Netgsm'in beklediği ulusal formata çevirir: '5321112233'.

    Kabul edilenler: '+90 532 111 22 33', '0532...', '90532...', '532...'.
    """
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("90") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


class SmsProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def send(self, *, to: str, body: str) -> SmsResult:
        """Tek alıcıya SMS gönderir; hata durumunda ok=False döner, raise etmez."""


class MockSmsProvider(SmsProvider):
    """Konsol/log simülasyonu — demo ve geliştirme için mevcut davranış."""

    name = "mock"

    def send(self, *, to: str, body: str) -> SmsResult:
        logger.info("📱 [SMS-MOCK] → %s · %s", to, body)
        print(f"\n{'=' * 60}")
        print("📱 SMS (SİMÜLASYON)")
        print(f"   Alıcı : {to}")
        print(f"   Mesaj : {body}")
        print(f"{'=' * 60}")
        return SmsResult(ok=True, provider=self.name)


class NetgsmSmsProvider(SmsProvider):
    """Netgsm REST v2 — https://api.netgsm.com.tr/sms/rest/v2/send

    Kimlik: usercode/password Basic Auth; `msgheader` operatör onaylı
    gönderici başlığıdır. Yanıt: {"code": "00", "jobid": "..."} (00 = kabul).
    """

    name = "netgsm"
    _ENDPOINT = "https://api.netgsm.com.tr/sms/rest/v2/send"

    def send(self, *, to: str, body: str) -> SmsResult:
        import httpx

        s = get_settings()
        number = netgsm_number(to)
        if len(number) != 10 or not number.startswith("5"):
            return SmsResult(ok=False, provider=self.name, error=f"invalid_number:{to!r}")
        try:
            resp = httpx.post(
                self._ENDPOINT,
                auth=(s.netgsm_usercode, s.netgsm_password),
                json={
                    "msgheader": s.netgsm_msgheader,
                    "encoding": "TR",
                    "messages": [{"msg": body, "no": number}],
                },
                timeout=s.sms_timeout,
            )
        except Exception as exc:  # noqa: BLE001 — SMS arızası akışı bozamaz
            logger.warning("netgsm_send_failed to=%s error=%s", number, exc)
            return SmsResult(ok=False, provider=self.name, error=str(exc))

        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        code = str(payload.get("code", "")) or (f"http_{resp.status_code}" if resp.status_code != 200 else "")
        if resp.status_code == 200 and code == "00":
            job_id = str(payload.get("jobid", "")) or None
            logger.info("netgsm_send_ok to=%s jobid=%s", number, job_id)
            return SmsResult(ok=True, provider=self.name, message_id=job_id)

        logger.warning("netgsm_send_rejected to=%s code=%s body=%s", number, code, resp.text[:200])
        return SmsResult(ok=False, provider=self.name, error=f"netgsm_code:{code}")


def netgsm_configured() -> bool:
    s = get_settings()
    return bool(s.netgsm_usercode and s.netgsm_password and s.netgsm_msgheader)


def get_sms_provider() -> SmsProvider:
    """Aktif SMS sağlayıcısını döndürür.

    `sms_provider=netgsm` ama kimlik bilgileri eksikse SESSİZCE mock'a düşmek
    yerine yüksek sesle loglayıp mock kullanırız — hasta mesaj almıyorsa bunun
    log'da ve /health/ready'de görünür olması gerekir.
    """
    s = get_settings()
    if s.sms_provider == "netgsm":
        if netgsm_configured():
            return NetgsmSmsProvider()
        logger.error(
            "sms_provider=netgsm seçili ama NETGSM_USERCODE/PASSWORD/MSGHEADER eksik — "
            "mock'a düşülüyor, HASTALAR GERÇEK SMS ALMIYOR."
        )
    return MockSmsProvider()


def sms_capabilities() -> dict:
    """Health/ready raporu için SMS sağlayıcı durumu."""
    s = get_settings()
    misconfigured = s.sms_provider == "netgsm" and not netgsm_configured()
    return {
        "configured_provider": s.sms_provider,
        "active_provider": get_sms_provider().name,
        "real_delivery": s.sms_provider == "netgsm" and netgsm_configured(),
        "misconfigured": misconfigured,
    }
