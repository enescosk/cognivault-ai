"""Harici API çağrılarına gönderilen alanlar için sertleştirilmiş validation şemaları.

Bu modülün amacı, kullanıcı serbest metninden çıkarılan değerlerin (şirket adı,
lokasyon, amaç) Google Places, web araması, e-posta taslakları gibi *outbound*
çağrılara aktarılmadan önce normalize edilmesi ve injection vektörlerinin
süzülmesidir.

Tehditler:
  - SQL injection karakterleri (`'`, `"`, `;`, `--`)
  - Shell injection (`` ` ``, `$`, `|`, `&`)
  - Path traversal / scheme injection (`/`, `\\`)
  - HTML/XSS (`<`, `>`)
  - ReDoS — uzunluk sınırı + sade regex kullanılır
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


# Yasaklı karakter seti — bu karakterler hiçbir outbound alanında olmamalı.
# Liste deliberately açık tutuluyor: < > " ' ; ( ) & \ | `
_FORBIDDEN_CHARS = set("<>\"';()&\\|`$")

# İzin verilen Unicode karakter sınıfları — Türkçe + İngilizce harf, rakam,
# tire, nokta, virgül, boşluk. Daha fazlasını gerektiren senaryoda regex
# genişletilir.
_ALLOWED_PATTERN = re.compile(r"^[\w\sÇĞİÖŞÜçğıöşü.,\-]+$", re.UNICODE)


def _normalize_and_validate(value: str, *, field_name: str, max_len: int) -> str:
    """Tek yerden normalize + güvenlik kontrolü. ValueError fırlatabilir."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} bir string olmalı")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} boş olamaz")
    if len(cleaned) > max_len:
        raise ValueError(f"{field_name} maksimum {max_len} karakter olabilir (mevcut: {len(cleaned)})")
    # Yasaklı karakter taraması — tek bir tane bile yeterli sebep
    forbidden_hit = next((c for c in cleaned if c in _FORBIDDEN_CHARS), None)
    if forbidden_hit is not None:
        raise ValueError(f"{field_name} yasaklı karakter içeriyor: {forbidden_hit!r}")
    # Pozitif allowlist — sadece beklenen karakter sınıfları geçer
    if not _ALLOWED_PATTERN.match(cleaned):
        raise ValueError(f"{field_name} sadece harf, rakam, '.', ',', '-' içerebilir")
    return cleaned


class CompanyOutreachRequest(BaseModel):
    """Harici şirket araması / Google Places sorgusu için sertleştirilmiş kontrat.

    `orchestrator.extract_outreach_terms()` çıktısı bu modele dönüştürülerek
    güvenli alanlar elde edilir. Validation hatası ValueError yayar — caller
    None döndürüp normal sohbet akışına dönmelidir.
    """

    company_name: str = Field(..., min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=50)
    purpose: str | None = Field(default=None, max_length=200)

    @field_validator("company_name")
    @classmethod
    def _v_company(cls, v: str) -> str:
        return _normalize_and_validate(v, field_name="company_name", max_len=100)

    @field_validator("location")
    @classmethod
    def _v_location(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _normalize_and_validate(v, field_name="location", max_len=50)

    @field_validator("purpose")
    @classmethod
    def _v_purpose(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        return _normalize_and_validate(v, field_name="purpose", max_len=200)


def safe_outreach_terms(raw: dict | None) -> dict | None:
    """Ham dict → temizlenmiş CompanyOutreachRequest dict'i. None döner if invalid."""
    if not raw:
        return None
    company = raw.get("company") or raw.get("company_name")
    if not company:
        return None
    try:
        validated = CompanyOutreachRequest(
            company_name=str(company),
            location=raw.get("location") or None,
            purpose=raw.get("purpose") or None,
        )
    except ValueError:
        return None
    out = validated.model_dump()
    # Eski caller'lar `company` key bekliyor — geri uyumluluk için map'le
    out["company"] = out.pop("company_name")
    return out
