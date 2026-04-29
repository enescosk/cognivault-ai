from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

from app.core.config import get_settings
from app.models import IntelligenceSourceKind, LeadContactKind


PHONE_RE = re.compile(r"(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{2}[\s.-]?\d{2}")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass(frozen=True)
class ExtractedContact:
    kind: LeadContactKind
    value: str
    normalized_value: str
    confidence: int


@dataclass(frozen=True)
class ConnectorLead:
    organization_name: str
    description: str | None
    location: str | None
    source_url: str | None
    source_kind: IntelligenceSourceKind
    confidence: int
    consent_basis: str
    provenance: dict
    contacts: list[ExtractedContact] = field(default_factory=list)


def normalize_phone(value: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", value)
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def extract_contacts(text: str) -> list[ExtractedContact]:
    contacts: list[ExtractedContact] = []
    seen: set[tuple[str, str]] = set()
    for match in PHONE_RE.findall(text):
        normalized = normalize_phone(match)
        key = (LeadContactKind.PHONE.value, normalized)
        if len(normalized) >= 10 and key not in seen:
            seen.add(key)
            contacts.append(
                ExtractedContact(
                    kind=LeadContactKind.PHONE,
                    value=match.strip(),
                    normalized_value=normalized,
                    confidence=82,
                )
            )
    for match in EMAIL_RE.findall(text):
        normalized = match.strip().lower()
        key = (LeadContactKind.EMAIL.value, normalized)
        if key not in seen:
            seen.add(key)
            contacts.append(
                ExtractedContact(
                    kind=LeadContactKind.EMAIL,
                    value=match.strip(),
                    normalized_value=normalized,
                    confidence=88,
                )
            )
    return contacts


class IntelligenceConnector:
    source_kind: IntelligenceSourceKind

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        raise NotImplementedError


CURATED_PUBLIC_COMPANIES = [
    # ── HASTANELER — Medipol ──────────────────────────────────────────────────
    {
        "keys": [
            "medipol", "medipol hastanesi", "medipol hospital",
            "medipol ataşehir", "medipol atasehir", "ataşehir medipol", "atasehir medipol",
            "medipol ataşehir şubesi", "medipol atasehir subesi",
        ],
        "organization_name": "Medipol Mega Üniversite Hastanesi",
        "description": "İstanbul Medipol Üniversitesi bünyesinde hizmet veren özel hastane zinciri. Randevu ve bilgi hattı: 444 70 00.",
        "location": "TEM Avrupa Otoyolu Göztepe Çıkışı No:1, 34214 Bağcılar / İstanbul",
        "source_url": "https://www.medipol.com.tr/iletisim",
        "source_name": "Medipol Hastanesi resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 70 00", 95),
            (LeadContactKind.EMAIL, "info@medipol.com.tr", 85),
        ],
    },
    {
        "keys": [
            "medipol pendik", "pendik medipol",
            "medipol camlica", "medipol çamlıca", "çamlıca medipol",
        ],
        "organization_name": "Medipol Pendik / Çamlıca Hastanesi",
        "description": "Medipol hastane grubu Anadolu yakası şubeleri.",
        "location": "İstanbul, Türkiye",
        "source_url": "https://www.medipol.com.tr/iletisim",
        "source_name": "Medipol Hastanesi resmi iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "444 70 00", 92),
        ],
    },
    # ── HASTANELER — Acıbadem ─────────────────────────────────────────────────
    {
        "keys": [
            "acıbadem", "acibadem", "acıbadem hastanesi", "acibadem hastanesi",
            "acıbadem ataşehir", "acibadem atasehir",
        ],
        "organization_name": "Acıbadem Hastanesi",
        "description": "Acıbadem Sağlık Grubu — Türkiye genelinde özel hastane zinciri.",
        "location": "Acıbadem Mah. Çeçen Sk. No:2, 34660 Üsküdar / İstanbul",
        "source_url": "https://www.acibadem.com.tr/iletisim/",
        "source_name": "Acıbadem Hastanesi resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 44 44", 95),
        ],
    },
    {
        "keys": [
            "acıbadem taksim", "acibadem taksim",
            "acıbadem fulya", "acibadem fulya",
            "acıbadem kadıköy", "acibadem kadikoy",
            "acıbadem bakırköy", "acibadem bakirkoy",
            "acıbadem maslak", "acibadem maslak",
            "acıbadem international", "acibadem international",
        ],
        "organization_name": "Acıbadem Hastanesi (Şube)",
        "description": "Acıbadem Sağlık Grubu İstanbul şubesi.",
        "location": "İstanbul, Türkiye",
        "source_url": "https://www.acibadem.com.tr/hastaneler/",
        "source_name": "Acıbadem Hastaneleri sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "444 44 44", 92),
        ],
    },
    # ── HASTANELER — Memorial ─────────────────────────────────────────────────
    {
        "keys": [
            "memorial", "memorial hastanesi", "memorial hospital",
            "memorial şişli", "memorial sisli",
            "memorial ataşehir", "memorial atasehir",
            "memorial ankara", "memorial hizmet",
        ],
        "organization_name": "Memorial Hastanesi",
        "description": "Memorial Sağlık Grubu — Türkiye genelinde özel hastane ve klinik zinciri.",
        "location": "Okmeydanı Cad. No:35, 34384 Şişli / İstanbul",
        "source_url": "https://www.memorial.com.tr/iletisim",
        "source_name": "Memorial Hastanesi resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 7 888", 94),
        ],
    },
    # ── HASTANELER — Liv Hospital ─────────────────────────────────────────────
    {
        "keys": [
            "liv hospital", "liv hastanesi",
            "liv ulus", "liv vadistanbul",
        ],
        "organization_name": "Liv Hospital",
        "description": "Liv Hospital Grubu — JCI akreditasyonlu uluslararası özel hastane.",
        "location": "Ulus Mahallesi, Ahmet Adnan Saygun Cad. No:35, 34340 Beşiktaş / İstanbul",
        "source_url": "https://www.livhospital.com/tr/iletisim",
        "source_name": "Liv Hospital resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 54 84", 93),
            (LeadContactKind.EMAIL, "info@livhospital.com", 85),
        ],
    },
    # ── HASTANELER — Koç Sağlık / American Hospital ───────────────────────────
    {
        "keys": [
            "american hospital", "amerikan hastanesi",
            "koç sağlık", "koc saglik", "vkv amerikan hastanesi",
        ],
        "organization_name": "VKV Amerikan Hastanesi",
        "description": "Vehbi Koç Vakfı bünyesinde faaliyet gösteren VKV Amerikan Hastanesi.",
        "location": "Güzelbahçe Sok. No:20, 34365 Nişantaşı / İstanbul",
        "source_url": "https://www.americanhospitaltr.com/tr/iletisim",
        "source_name": "VKV Amerikan Hastanesi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 444 37 77", 93),
        ],
    },
    # ── HASTANELER — Florence Nightingale ────────────────────────────────────
    {
        "keys": [
            "florence nightingale", "florence",
            "ataşehir florence", "atasehir florence",
            "şişli florence", "sisli florence",
            "gayrettepe florence",
        ],
        "organization_name": "Group Florence Nightingale Hastanesi",
        "description": "Group Florence Nightingale İstanbul hastaneleri — Şişli, Ataşehir, Gayrettepe.",
        "location": "Abide-i Hürriyet Cad. No:290, 34381 Şişli / İstanbul",
        "source_url": "https://groupflorence.com/tr/iletisim/",
        "source_name": "Group Florence Nightingale resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "0850 711 60 60", 93),
        ],
    },
    # ── HASTANELER — Medistate ────────────────────────────────────────────────
    {
        "keys": [
            "medistate", "medistate hastanesi",
            "medistate çekmeköy", "medistate cekmekoy",
            "medistate kavacık", "medistate kavacik",
        ],
        "organization_name": "Medistate Hastanesi",
        "description": "Özel Medistate Hastanesi; Çekmeköy ve Kavacık şubeleriyle hizmet vermektedir.",
        "location": "Merkez, Erenler Cd No:16, 34782 Çekmeköy / İstanbul",
        "source_url": "https://www.medistate.com.tr/iletisim",
        "source_name": "Medistate Hastanesi resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 44 13", 94),
            (LeadContactKind.EMAIL, "bilgi@medistate.com.tr", 86),
        ],
    },
    # ── HASTANELER — Özel Türk Hastaneleri ───────────────────────────────────
    {
        "keys": [
            "nişantaşı hastanesi", "nisantasi hastanesi",
            "özel nişantaşı", "ozel nisantasi",
        ],
        "organization_name": "Özel Nişantaşı Hastanesi",
        "description": "Özel Nişantaşı Hastanesi — genel cerrahi, ortopedi, kardiyoloji.",
        "location": "Teşvikiye Mah. Vali Konağı Cad. No:67, 34365 Nişantaşı / İstanbul",
        "source_url": "https://www.nisantasihastanesi.com/iletisim",
        "source_name": "Nişantaşı Hastanesi resmi iletişim sayfası",
        "confidence": 88,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 219 50 00", 88),
        ],
    },
    {
        "keys": [
            "hisar intercontinental", "hisar hospital", "hisar hastanesi",
            "hisar intercontinental hospital",
        ],
        "organization_name": "Hisar Intercontinental Hospital",
        "description": "Özel Hisar Intercontinental Hastanesi — uluslararası hasta hizmetleri.",
        "location": "Saray Mah. Siteyolu Cad. No:7, 34768 Ümraniye / İstanbul",
        "source_url": "https://www.hisarhospital.com/tr/iletisim",
        "source_name": "Hisar Intercontinental Hospital iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 216 559 00 00", 91),
            (LeadContactKind.EMAIL, "info@hisarhospital.com", 84),
        ],
    },
    {
        "keys": [
            "bahçelievler medical park", "bahcelievler medical park",
            "medical park bahçelievler", "medical park hastanesi",
            "medical park", "medicalpark",
        ],
        "organization_name": "Medical Park Hastanesi",
        "description": "Medical Park Sağlık Grubu — Türkiye genelinde yaygın özel hastane zinciri.",
        "location": "İstanbul, Türkiye",
        "source_url": "https://www.medicalpark.com.tr/iletisim",
        "source_name": "Medical Park resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 1 444", 93),
        ],
    },
    {
        "keys": [
            "dünya göz", "dunya goz", "dünya göz hastanesi", "dunya goz hastanesi",
            "dünya göz kliniği",
        ],
        "organization_name": "Dünya Göz Hastanesi",
        "description": "Dünya Göz Grubu — göz sağlığı alanında uzmanlaşmış hastane ve klinik zinciri.",
        "location": "Büyükdere Cad. No:149, 34394 Şişli / İstanbul",
        "source_url": "https://www.dunyagoz.com/iletisim",
        "source_name": "Dünya Göz Hastanesi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 35 20", 93),
        ],
    },
    {
        "keys": [
            "eye center", "eye center hastanesi", "göz merkezi",
            "lazer göz", "lazer goz",
        ],
        "organization_name": "Dünya Göz / Eye Center",
        "description": "Göz muayene, lazer ve katarakt tedavisi merkezi.",
        "location": "İstanbul, Türkiye",
        "source_url": "https://www.dunyagoz.com/iletisim",
        "source_name": "Dünya Göz iletişim sayfası",
        "confidence": 88,
        "contacts": [
            (LeadContactKind.PHONE, "444 35 20", 88),
        ],
    },
    # ── HASTANELER — Ankara ───────────────────────────────────────────────────
    {
        "keys": [
            "güven hastanesi", "guven hastanesi", "ankara güven hastanesi",
            "özel güven hastanesi",
        ],
        "organization_name": "Güven Hastanesi Ankara",
        "description": "Ankara'da faaliyet gösteren özel Güven Hastanesi.",
        "location": "Emek Mah. Dilara Sok. No:1, 06500 Çankaya / Ankara",
        "source_url": "https://www.guvenhastanesi.com.tr/iletisim",
        "source_name": "Güven Hastanesi Ankara iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 457 27 27", 91),
        ],
    },
    {
        "keys": [
            "bayındır hastanesi", "bayindir hastanesi",
            "ankara bayındır", "kavaklidere bayindır",
        ],
        "organization_name": "Bayındır Hastanesi Ankara",
        "description": "Özel Bayındır Hastanesi Ankara şubeleri.",
        "location": "Söğütözü Cad. No:18, 06510 Söğütözü / Ankara",
        "source_url": "https://www.bayindirhospital.com.tr/iletisim",
        "source_name": "Bayındır Hastanesi iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 576", 91),
        ],
    },
    # ── DEVLET HASTANELERİ ────────────────────────────────────────────────────
    {
        "keys": [
            "marmara üniversitesi hastanesi", "marmara universitesi hastanesi",
            "marmara hastanesi pendik",
        ],
        "organization_name": "Marmara Üniversitesi Pendik Eğitim ve Araştırma Hastanesi",
        "description": "Marmara Üniversitesi'ne bağlı eğitim ve araştırma hastanesi.",
        "location": "Fevzi Çakmak Mah. Muhsin Yazıcıoğlu Cad. No:10, 34899 Pendik / İstanbul",
        "source_url": "https://pendik.marmara.edu.tr/iletisim",
        "source_name": "Marmara Üniversitesi Hastanesi resmi sayfası",
        "confidence": 90,
        "contacts": [
            (LeadContactKind.PHONE, "+90 216 657 06 06", 90),
        ],
    },
    {
        "keys": [
            "cerrahpaşa", "cerrahpasa", "istanbul cerrahpaşa",
            "cerrahpaşa tıp fakültesi", "cerrahpasa tip fakultesi",
        ],
        "organization_name": "İstanbul Cerrahpaşa Tıp Fakültesi Hastanesi",
        "description": "İstanbul Üniversitesi-Cerrahpaşa bünyesinde devlet üniversitesi hastanesi.",
        "location": "Kocamustafapaşa Cad. No:34, 34098 Fatih / İstanbul",
        "source_url": "https://hastane.istanbul.edu.tr/iletisim",
        "source_name": "Cerrahpaşa Hastanesi resmi iletişim sayfası",
        "confidence": 90,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 414 30 00", 90),
        ],
    },
    {
        "keys": [
            "hacettepe hastanesi", "hacettepe universitesi hastanesi",
            "hacettepe university hospital",
        ],
        "organization_name": "Hacettepe Üniversitesi Hastaneleri",
        "description": "Hacettepe Üniversitesi eğitim ve araştırma hastaneleri — Ankara.",
        "location": "Hacettepe Mah. 06230 Altındağ / Ankara",
        "source_url": "https://www.hacettepe.edu.tr/iletisim",
        "source_name": "Hacettepe Üniversitesi Hastaneleri sayfası",
        "confidence": 90,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 305 50 00", 90),
        ],
    },
    # ── BANKALAR ──────────────────────────────────────────────────────────────
    {
        "keys": ["akbank", "ak bank"],
        "organization_name": "Akbank",
        "description": "Akbank müşteri iletişim merkezi — bankacılık işlemleri.",
        "location": "Akbank Müşteri İletişim Merkezi, Türkiye",
        "source_url": "https://www.akbank.com/tr-tr/genel/Sayfalar/musteri-iletisim-merkezi.aspx",
        "source_name": "Akbank resmi müşteri iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 25 25", 95),
            (LeadContactKind.PHONE, "0850 222 25 25", 93),
        ],
    },
    {
        "keys": ["garanti bbva", "garanti bankası", "garanti bankasi", "garanti", "bbva türkiye"],
        "organization_name": "Garanti BBVA",
        "description": "Garanti BBVA müşteri hizmetleri — bankacılık ve kart işlemleri.",
        "location": "Garanti BBVA Müşteri Hizmetleri, Türkiye",
        "source_url": "https://www.garantibbva.com.tr/bireysel/iletisim.page",
        "source_name": "Garanti BBVA resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 333", 95),
            (LeadContactKind.PHONE, "0850 222 0 333", 93),
        ],
    },
    {
        "keys": ["iş bankası", "is bankasi", "türkiye iş bankası", "isbank"],
        "organization_name": "Türkiye İş Bankası",
        "description": "Türkiye İş Bankası müşteri hizmetleri.",
        "location": "İş Bankası Genel Müdürlüğü, Levent / İstanbul",
        "source_url": "https://www.isbank.com.tr/iletisim",
        "source_name": "İş Bankası resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 100", 95),
        ],
    },
    {
        "keys": ["yapı kredi", "yapi kredi", "yapı kredi bankası", "ykb"],
        "organization_name": "Yapı Kredi Bankası",
        "description": "Yapı Kredi Bankası müşteri iletişim merkezi.",
        "location": "Yapı Kredi Genel Müdürlüğü, Kozyatağı / İstanbul",
        "source_url": "https://www.yapikredi.com.tr/iletisim",
        "source_name": "Yapı Kredi resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 444", 95),
        ],
    },
    {
        "keys": ["ziraat bankası", "ziraat bankasi", "t.c. ziraat bankası", "ziraat"],
        "organization_name": "Ziraat Bankası",
        "description": "T.C. Ziraat Bankası müşteri hizmetleri.",
        "location": "Ziraat Bankası Genel Müdürlüğü, Ankara",
        "source_url": "https://www.ziraatbank.com.tr/tr/iletisim",
        "source_name": "Ziraat Bankası resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 100", 95),
        ],
    },
    {
        "keys": ["vakıfbank", "vakifbank", "t.c. vakıfbank", "vakıf bank"],
        "organization_name": "VakıfBank",
        "description": "Vakıflar Bankası müşteri hizmetleri.",
        "location": "VakıfBank Genel Müdürlüğü, Ankara",
        "source_url": "https://www.vakifbank.com.tr/iletisim.aspx",
        "source_name": "VakıfBank resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 724", 95),
        ],
    },
    {
        "keys": ["halkbank", "halk bankası", "halk bankasi", "t.c. halkbank"],
        "organization_name": "Halkbank",
        "description": "T.C. Halkbank müşteri hizmetleri.",
        "location": "Halkbank Genel Müdürlüğü, Ankara",
        "source_url": "https://www.halkbank.com.tr/iletisim",
        "source_name": "Halkbank resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 400", 94),
        ],
    },
    {
        "keys": ["bnp paribas türkiye", "bnp türkiye", "bnp paribas cardif", "teb", "türk ekonomi bankası"],
        "organization_name": "TEB — Türk Ekonomi Bankası",
        "description": "Türk Ekonomi Bankası / TEB müşteri hizmetleri.",
        "location": "TEB Genel Müdürlüğü, Mecidiyeköy / İstanbul",
        "source_url": "https://www.teb.com.tr/iletisim/",
        "source_name": "TEB resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 832", 93),
        ],
    },
    {
        "keys": ["qnb finansbank", "finansbank", "qnb"],
        "organization_name": "QNB Finansbank",
        "description": "QNB Finansbank müşteri hizmetleri.",
        "location": "QNB Finansbank Genel Müdürlüğü, Esentepe / İstanbul",
        "source_url": "https://www.qnbfinansbank.com/iletisim",
        "source_name": "QNB Finansbank resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 123", 93),
        ],
    },
    {
        "keys": ["denizbank", "deniz bank"],
        "organization_name": "DenizBank",
        "description": "DenizBank müşteri hizmetleri.",
        "location": "DenizBank Genel Müdürlüğü, Büyükdere / İstanbul",
        "source_url": "https://www.denizbank.com/iletisim/",
        "source_name": "DenizBank resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 800", 93),
        ],
    },
    {
        "keys": ["ing bank türkiye", "ing bank", "ing türkiye"],
        "organization_name": "ING Bank Türkiye",
        "description": "ING Bank Türkiye müşteri hizmetleri.",
        "location": "ING Bank Türkiye Genel Müdürlüğü, Maslak / İstanbul",
        "source_url": "https://www.ingbank.com.tr/tr/iletisim",
        "source_name": "ING Bank Türkiye iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 464", 92),
        ],
    },
    # ── TELEKOMÜNİKASYON ──────────────────────────────────────────────────────
    {
        "keys": [
            "turkcell", "turkcell iletişim", "turkcell müşteri hizmetleri",
            "turkcell mağazası",
        ],
        "organization_name": "Turkcell",
        "description": "Turkcell müşteri hizmetleri — hat, internet, fatura işlemleri.",
        "location": "Turkcell Genel Müdürlüğü, Maltepe Park Ataşehir / İstanbul",
        "source_url": "https://www.turkcell.com.tr/iletisim",
        "source_name": "Turkcell resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "532", 95),
            (LeadContactKind.PHONE, "0532 532 53 53", 93),
        ],
    },
    {
        "keys": [
            "vodafone türkiye", "vodafone", "vodafone tr",
            "vodafone müşteri hizmetleri",
        ],
        "organization_name": "Vodafone Türkiye",
        "description": "Vodafone Türkiye müşteri hizmetleri — hat, veri, kurumsal çözümler.",
        "location": "Vodafone Türkiye Genel Müdürlüğü, Ümraniye / İstanbul",
        "source_url": "https://www.vodafone.com.tr/vodafone-hakkinda/iletisim",
        "source_name": "Vodafone Türkiye iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "542", 95),
            (LeadContactKind.PHONE, "0542 542 00 00", 92),
        ],
    },
    {
        "keys": [
            "türk telekom", "turk telekom", "tt", "turknet",
            "türk telekom internet", "türk telekom müşteri hizmetleri",
        ],
        "organization_name": "Türk Telekom",
        "description": "Türk Telekom müşteri hizmetleri — sabit hat, internet, ADSL, fiber.",
        "location": "Türk Telekom Genel Müdürlüğü, Ankara",
        "source_url": "https://www.turktelekom.com.tr/iletisim",
        "source_name": "Türk Telekom resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 1 444", 95),
        ],
    },
    # ── E-TİCARET / TEKNOLOJİ ────────────────────────────────────────────────
    {
        "keys": ["trendyol", "trendyol.com", "trendyol müşteri hizmetleri"],
        "organization_name": "Trendyol",
        "description": "Trendyol — Türkiye'nin lider e-ticaret platformu müşteri hizmetleri.",
        "location": "Trendyol Genel Müdürlüğü, Kozyatağı / İstanbul",
        "source_url": "https://www.trendyol.com/iletisim",
        "source_name": "Trendyol resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "0850 333 09 09", 94),
            (LeadContactKind.EMAIL, "destek@trendyol.com", 88),
        ],
    },
    {
        "keys": ["hepsiburada", "hepsiburada.com", "hepsiburada müşteri hizmetleri"],
        "organization_name": "Hepsiburada",
        "description": "Hepsiburada — e-ticaret platformu müşteri hizmetleri.",
        "location": "Hepsiburada Genel Müdürlüğü, Bağcılar / İstanbul",
        "source_url": "https://www.hepsiburada.com/iletisim",
        "source_name": "Hepsiburada resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "0850 252 40 00", 93),
        ],
    },
    {
        "keys": ["getir", "getir market", "getir sipariş", "getir destek"],
        "organization_name": "Getir",
        "description": "Getir — hızlı teslimat uygulaması müşteri hizmetleri.",
        "location": "Getir Genel Müdürlüğü, Şişli / İstanbul",
        "source_url": "https://getir.com/tr/iletisim/",
        "source_name": "Getir resmi iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.EMAIL, "help@getir.com", 88),
        ],
    },
    {
        "keys": ["n11", "n11.com", "n11 müşteri hizmetleri"],
        "organization_name": "N11",
        "description": "N11 — e-ticaret platformu müşteri hizmetleri.",
        "location": "N11 Genel Müdürlüğü, İstanbul",
        "source_url": "https://www.n11.com/iletisim",
        "source_name": "N11 iletişim sayfası",
        "confidence": 90,
        "contacts": [
            (LeadContactKind.PHONE, "0850 532 11 00", 90),
        ],
    },
    # ── HAVAYOLLARI ───────────────────────────────────────────────────────────
    {
        "keys": [
            "türk hava yolları", "turk hava yollari", "thy",
            "turkish airlines", "türk hava yolu",
        ],
        "organization_name": "Türk Hava Yolları (THY)",
        "description": "Türk Hava Yolları müşteri hizmetleri — uçuş, bilet, mil işlemleri.",
        "location": "THY Genel Müdürlüğü, Yeşilköy / İstanbul",
        "source_url": "https://www.turkishairlines.com/tr-tr/iletisim/",
        "source_name": "THY resmi iletişim sayfası",
        "confidence": 95,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 849", 95),
            (LeadContactKind.PHONE, "0850 333 0 849", 93),
        ],
    },
    {
        "keys": [
            "pegasus", "pegasus hava yolları", "pegasus airlines",
            "pegasus havayolları",
        ],
        "organization_name": "Pegasus Hava Yolları",
        "description": "Pegasus Airlines müşteri hizmetleri — uçuş, bilet, check-in.",
        "location": "Pegasus Genel Müdürlüğü, Kurtköy / İstanbul",
        "source_url": "https://www.flypgs.com/tr/iletisim",
        "source_name": "Pegasus Airlines iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "0888 228 12 12", 94),
        ],
    },
    {
        "keys": ["sunexpress", "sun express", "sunexpress hava yolları"],
        "organization_name": "SunExpress",
        "description": "SunExpress havayolu müşteri hizmetleri.",
        "location": "SunExpress Genel Müdürlüğü, Antalya",
        "source_url": "https://www.sunexpress.com/tr/iletisim/",
        "source_name": "SunExpress iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "0850 225 46 79", 91),
        ],
    },
    # ── HAVALİMANLARI ─────────────────────────────────────────────────────────
    {
        "keys": [
            "istanbul havalimanı", "istanbul havalimani",
            "ist havalimanı", "ist airport",
            "iğa havalimanı",
        ],
        "organization_name": "İstanbul Havalimanı (İGA)",
        "description": "İstanbul Havalimanı genel bilgi ve yolcu hizmetleri.",
        "location": "Tayakadın Köyü Mevkii, 34283 Arnavutköy / İstanbul",
        "source_url": "https://www.istairport.com/tr/iletisim",
        "source_name": "İstanbul Havalimanı resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 1 442", 94),
        ],
    },
    {
        "keys": [
            "sabiha gökçen", "sabiha gokcen",
            "saw havalimanı", "saw airport",
            "pendik havalimanı",
        ],
        "organization_name": "Sabiha Gökçen Uluslararası Havalimanı",
        "description": "İstanbul'un Anadolu yakasında yer alan uluslararası havalimanı.",
        "location": "Sanayi Mah. Havalimanı Bul. No:3, 34912 Pendik / İstanbul",
        "source_url": "https://www.sabihagokcen.aero/tr/iletisim",
        "source_name": "Sabiha Gökçen Havalimanı resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "+90 216 588 80 00", 93),
        ],
    },
    {
        "keys": [
            "esenboğa havalimanı", "esenboga havalimani",
            "ankara havalimanı", "ankara airport",
        ],
        "organization_name": "Ankara Esenboğa Havalimanı",
        "description": "Ankara Esenboğa Uluslararası Havalimanı — iç ve dış hatlar.",
        "location": "Esenboğa Havalimanı, 06790 Akyurt / Ankara",
        "source_url": "https://www.esenbogaairport.com/tr/iletisim",
        "source_name": "Esenboğa Havalimanı iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 590 40 00", 92),
        ],
    },
    # ── SİGORTA ───────────────────────────────────────────────────────────────
    {
        "keys": ["allianz türkiye", "allianz sigorta", "allianz"],
        "organization_name": "Allianz Sigorta",
        "description": "Allianz Sigorta Türkiye müşteri hizmetleri — araç, sağlık, konut sigortası.",
        "location": "Allianz Tower, Küçükbakkalköy Mah., Ataşehir / İstanbul",
        "source_url": "https://www.allianz.com.tr/tr_TR/iletisim.html",
        "source_name": "Allianz Sigorta iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 25 56", 93),
        ],
    },
    {
        "keys": ["axa sigorta", "axa türkiye", "axa"],
        "organization_name": "AXA Sigorta",
        "description": "AXA Sigorta Türkiye — sağlık, araç, seyahat sigortası.",
        "location": "Levent, İstanbul",
        "source_url": "https://www.axasigorta.com.tr/iletisim",
        "source_name": "AXA Sigorta iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 292", 92),
        ],
    },
    {
        "keys": ["mapfre sigorta", "mapfre türkiye", "mapfre"],
        "organization_name": "Mapfre Sigorta",
        "description": "Mapfre Sigorta Türkiye müşteri hizmetleri.",
        "location": "Esentepe, İstanbul",
        "source_url": "https://www.mapfresigorta.com.tr/iletisim",
        "source_name": "Mapfre Sigorta iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 627", 91),
        ],
    },
    {
        "keys": ["anadolu sigorta", "anadolu sigorta türkiye"],
        "organization_name": "Anadolu Sigorta",
        "description": "Anadolu Sigorta müşteri hizmetleri — araç, yangın, sağlık sigortası.",
        "location": "Anadolu Sigorta Genel Müdürlüğü, Levent / İstanbul",
        "source_url": "https://www.anadolusigorta.com.tr/tr/iletisim",
        "source_name": "Anadolu Sigorta iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "444 1 258", 91),
        ],
    },
    # ── ENERJİ ────────────────────────────────────────────────────────────────
    {
        "keys": ["igdaş", "igdas", "istanbul gaz", "istanbul gaz dağıtım", "doğalgaz istanbul"],
        "organization_name": "İGDAŞ — İstanbul Gaz Dağıtım",
        "description": "İGDAŞ doğalgaz arıza ve müşteri hizmetleri — İstanbul Avrupa yakası.",
        "location": "İGDAŞ Genel Müdürlüğü, Güngören / İstanbul",
        "source_url": "https://www.igdas.istanbul/iletisim",
        "source_name": "İGDAŞ resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "187", 95),
            (LeadContactKind.PHONE, "0212 473 20 00", 93),
        ],
    },
    {
        "keys": ["aksa gaz", "aksa doğalgaz", "istanbul anadolu yakası gaz", "aksa"],
        "organization_name": "AKSA Doğalgaz",
        "description": "AKSA Doğalgaz — İstanbul Anadolu yakası gaz dağıtım ve müşteri hizmetleri.",
        "location": "AKSA Genel Müdürlüğü, Ümraniye / İstanbul",
        "source_url": "https://www.aksa.com.tr/tr/iletisim",
        "source_name": "AKSA Doğalgaz resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "187", 95),
            (LeadContactKind.PHONE, "0850 200 02 02", 92),
        ],
    },
    {
        "keys": ["tedaş", "tedas", "elektrik dağıtım", "istanbul elektrik", "boğaziçi elektrik", "bEDAŞ", "bedas"],
        "organization_name": "Boğaziçi Elektrik / BEDAŞ",
        "description": "BEDAŞ — İstanbul Avrupa yakası elektrik dağıtım şirketi.",
        "location": "BEDAŞ Genel Müdürlüğü, Şişli / İstanbul",
        "source_url": "https://www.bedas.com.tr/iletisim",
        "source_name": "BEDAŞ resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "186", 95),
            (LeadContactKind.PHONE, "0212 422 04 00", 91),
        ],
    },
    {
        "keys": ["ayedaş", "ayedas", "anadolu elektrik", "istanbul anadolu elektrik"],
        "organization_name": "AYEDAŞ — Anadolu Yakası Elektrik Dağıtım",
        "description": "AYEDAŞ — İstanbul Anadolu yakası elektrik dağıtım şirketi.",
        "location": "AYEDAŞ Genel Müdürlüğü, Kadıköy / İstanbul",
        "source_url": "https://www.ayedas.com.tr/iletisim",
        "source_name": "AYEDAŞ resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "186", 95),
            (LeadContactKind.PHONE, "0216 468 55 00", 91),
        ],
    },
    {
        "keys": ["baskent gaz", "baskent dogalgaz", "başkent gaz", "başkent doğalgaz", "ankara gaz"],
        "organization_name": "Başkent Doğalgaz",
        "description": "Başkent Doğalgaz — Ankara ve çevre illerde gaz dağıtım ve müşteri hizmetleri.",
        "location": "Başkent Doğalgaz Genel Müdürlüğü, Ankara",
        "source_url": "https://www.baskentgaz.com.tr/iletisim",
        "source_name": "Başkent Doğalgaz iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "187", 95),
            (LeadContactKind.PHONE, "0312 295 35 35", 91),
        ],
    },
    # ── DEVLET KURUMLARI ──────────────────────────────────────────────────────
    {
        "keys": ["sgk", "sosyal güvenlik kurumu", "sosyal guvenlik kurumu", "ssk", "bağkur"],
        "organization_name": "Sosyal Güvenlik Kurumu (SGK)",
        "description": "SGK — emeklilik, sağlık ve iş sigortası işlemleri.",
        "location": "SGK Genel Müdürlüğü, Mithatpaşa Cad. Sıhhiye / Ankara",
        "source_url": "https://www.sgk.gov.tr/wps/portal/sgk/tr/iletisim",
        "source_name": "SGK resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "170", 95),
        ],
    },
    {
        "keys": ["ptt", "ptt kargo", "ptt bank", "türkiye posta"],
        "organization_name": "PTT",
        "description": "PTT — posta, kargo, PTT Bank işlemleri müşteri hizmetleri.",
        "location": "PTT Genel Müdürlüğü, Ankara",
        "source_url": "https://www.ptt.gov.tr/tr/iletisim",
        "source_name": "PTT resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "444 1 788", 93),
        ],
    },
    {
        "keys": [
            "belediye", "istanbul büyükşehir belediyesi", "ibb",
            "istanbul belediyesi", "ibb iletişim",
        ],
        "organization_name": "İstanbul Büyükşehir Belediyesi (İBB)",
        "description": "İstanbul Büyükşehir Belediyesi — şikayet, talep ve bilgi hizmetleri.",
        "location": "İBB Genel Müdürlüğü, Saraçhane / İstanbul",
        "source_url": "https://www.ibb.istanbul/iletisim",
        "source_name": "İBB resmi iletişim sayfası",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "153", 95),
            (LeadContactKind.PHONE, "0212 449 49 49", 92),
        ],
    },
    {
        "keys": ["ankara büyükşehir belediyesi", "ankaray", "ego", "asp ankara"],
        "organization_name": "Ankara Büyükşehir Belediyesi",
        "description": "Ankara Büyükşehir Belediyesi — şikayet, talep ve hizmet bilgisi.",
        "location": "Ankara Büyükşehir Belediyesi, Kızılay / Ankara",
        "source_url": "https://www.ankara.bel.tr/iletisim",
        "source_name": "Ankara Büyükşehir Belediyesi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "153", 94),
        ],
    },
    {
        "keys": ["nüfus müdürlüğü", "nufus mudurlugu", "kimlik", "nüfus cüzdanı", "pasaport"],
        "organization_name": "Nüfus Müdürlüğü / e-Devlet",
        "description": "Nüfus müdürlüğü randevu ve işlemler — e-Devlet üzerinden yapılabilir.",
        "location": "https://www.turkiye.gov.tr (e-Devlet)",
        "source_url": "https://e-randevu.nvi.gov.tr/",
        "source_name": "Nüfus ve Vatandaşlık İşleri e-Randevu",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "199", 93),
        ],
    },
    {
        "keys": ["emniyet müdürlüğü", "trafik tescil", "ehliyet", "pasaport müdürlüğü"],
        "organization_name": "İl Emniyet Müdürlüğü",
        "description": "Emniyet Müdürlüğü — pasaport, ehliyet, trafik tescil işlemleri. Randevu e-Devlet üzerinden alınır.",
        "location": "e-Randevu: https://e-randevu.pol.gov.tr/",
        "source_url": "https://e-randevu.pol.gov.tr/",
        "source_name": "Emniyet Müdürlüğü e-Randevu sistemi",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "155", 93),
        ],
    },
    # ── PERAKENDE / ZİNCİRLER ─────────────────────────────────────────────────
    {
        "keys": ["migros", "migros market", "migros türkiye"],
        "organization_name": "Migros",
        "description": "Migros Türkiye müşteri hizmetleri — market, online alışveriş.",
        "location": "Migros Genel Müdürlüğü, Ümraniye / İstanbul",
        "source_url": "https://www.migros.com.tr/iletisim",
        "source_name": "Migros resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "0850 200 38 38", 93),
        ],
    },
    {
        "keys": ["carrefoursa", "carrefour türkiye", "carrefour"],
        "organization_name": "CarrefourSA",
        "description": "CarrefourSA Türkiye müşteri hizmetleri.",
        "location": "CarrefourSA Genel Müdürlüğü, İstanbul",
        "source_url": "https://www.carrefoursa.com/iletisim",
        "source_name": "CarrefourSA iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "444 0 055", 91),
        ],
    },
    # ── SPOR TESİSLERİ ────────────────────────────────────────────────────────
    {
        "keys": [
            "macfit", "mac fit", "macfit spor", "macfit gym",
            "macfit ümraniye", "macfit umraniye", "macfit buyaka",
            "macfit şişli", "macfit kadıköy", "macfit levent",
        ],
        "organization_name": "MACFit",
        "description": "MACFit spor merkezi — Türkiye genelinde zincir fitness kulüpleri.",
        "location": "Türkiye genelinde çok şubeli",
        "source_url": "https://www.macfit.com/iletisim/",
        "source_name": "MACFit resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "0850 241 30 00", 93),
        ],
    },
    {
        "keys": ["wclub", "w club spor", "wclub fitness"],
        "organization_name": "WClub Fitness",
        "description": "WClub spor merkezi ve fitness kulübü.",
        "location": "İstanbul, Türkiye",
        "source_url": "https://www.wclub.com.tr/iletisim",
        "source_name": "WClub resmi iletişim sayfası",
        "confidence": 88,
        "contacts": [
            (LeadContactKind.PHONE, "0850 460 90 50", 88),
        ],
    },
    {
        "keys": [
            "galatasaray spor kulübü", "galatasaray", "gs",
            "galatasaray üyelik", "galatasaray bilet",
        ],
        "organization_name": "Galatasaray Spor Kulübü",
        "description": "Galatasaray Spor Kulübü — bilet, üyelik ve genel bilgi hattı.",
        "location": "TT Arena, Seyrantepe / İstanbul",
        "source_url": "https://www.galatasaray.org/tr/iletisim",
        "source_name": "Galatasaray Spor Kulübü iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "444 90 05", 92),
        ],
    },
    {
        "keys": [
            "fenerbahçe spor kulübü", "fenerbahçe", "fb",
            "fenerbahçe bilet", "fenerbahçe üyelik",
        ],
        "organization_name": "Fenerbahçe Spor Kulübü",
        "description": "Fenerbahçe SK — bilet, üyelik ve genel bilgi hattı.",
        "location": "Kadıköy / İstanbul",
        "source_url": "https://www.fenerbahce.org/iletisim",
        "source_name": "Fenerbahçe SK iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "0850 222 1907", 92),
        ],
    },
    # ── OTELLERveAVM ─────────────────────────────────────────────────────────
    {
        "keys": [
            "hilton istanbul", "hilton hotel istanbul",
            "hilton bomonti", "hilton bosphorus",
        ],
        "organization_name": "Hilton İstanbul",
        "description": "Hilton İstanbul oteli rezervasyon ve genel bilgi.",
        "location": "Cumhuriyet Cad. No:50, 34367 Harbiye / İstanbul",
        "source_url": "https://www.hilton.com/tr/hotels/isthitw-hilton-istanbul/",
        "source_name": "Hilton İstanbul resmi sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 315 60 00", 92),
        ],
    },
    {
        "keys": [
            "istanbul marriott", "marriott istanbul",
            "marriott şişli", "marriott asia",
        ],
        "organization_name": "İstanbul Marriott Hotel",
        "description": "Marriott İstanbul oteli rezervasyon ve genel bilgi.",
        "location": "Şişli / İstanbul",
        "source_url": "https://www.marriott.com/tr/hotels/travel/istlt-istanbul-marriott-hotel-asia/",
        "source_name": "Marriott İstanbul resmi sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 371 15 00", 91),
        ],
    },
    {
        "keys": ["istinye park", "istinyepark avm", "istinyepark"],
        "organization_name": "İstinye Park AVM",
        "description": "İstinye Park alışveriş merkezi — İstanbul Sarıyer.",
        "location": "İstinye Mah. İstinye Cad. No:1, 34460 Sarıyer / İstanbul",
        "source_url": "https://www.istinyepark.com/iletisim",
        "source_name": "İstinye Park resmi iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 345 55 55", 91),
        ],
    },
    {
        "keys": [
            "zorlu center", "zorlu avm", "zorlu psc",
            "zorlu center istanbul",
        ],
        "organization_name": "Zorlu Center",
        "description": "Zorlu Center — alışveriş, eğlence ve yaşam merkezi Beşiktaş / İstanbul.",
        "location": "Levazım Mah. Koru Sok. No:2, 34340 Beşiktaş / İstanbul",
        "source_url": "https://www.zorlucenter.com/iletisim",
        "source_name": "Zorlu Center iletişim sayfası",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 924 01 01", 91),
        ],
    },
    # ── DANIŞMANLIK ───────────────────────────────────────────────────────────
    {
        "keys": ["ods", "ods consulting", "ods consulting group"],
        "organization_name": "ODS Consulting Group",
        "description": "Uluslararası iş geliştirme ve ihracat danışmanlığı dahil yönetim danışmanlığı hizmetleri.",
        "location": "Kızılırmak Mah. Dumlupınar Bul. Next Level A Blok No:3, 06520 Çankaya / Ankara",
        "source_url": "https://ods.consulting/contact/",
        "source_name": "ODS Consulting iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 531 637 74 89", 92),
            (LeadContactKind.EMAIL, "contact@ods.consulting", 88),
        ],
    },
    # ── ÜNİVERSİTELER ────────────────────────────────────────────────────────
    {
        "keys": [
            "sabancı üniversitesi", "sabanci universitesi",
            "su sabancı", "sabancı uni",
        ],
        "organization_name": "Sabancı Üniversitesi",
        "description": "Sabancı Üniversitesi — Tuzla / İstanbul — akademik ve idari iletişim.",
        "location": "Orhanli, Tuzla / İstanbul 34956",
        "source_url": "https://www.sabanciuniv.edu/tr/bize-ulasin",
        "source_name": "Sabancı Üniversitesi resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "+90 216 483 90 00", 93),
            (LeadContactKind.EMAIL, "info@sabanciuniv.edu", 88),
        ],
    },
    {
        "keys": [
            "boğaziçi üniversitesi", "bogazici universitesi", "boun",
            "bogazici university",
        ],
        "organization_name": "Boğaziçi Üniversitesi",
        "description": "Boğaziçi Üniversitesi — Bebek / İstanbul.",
        "location": "34342 Bebek / İstanbul",
        "source_url": "https://www.boun.edu.tr/tr_TR/content/default.aspx",
        "source_name": "Boğaziçi Üniversitesi iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 359 45 23", 92),
        ],
    },
    {
        "keys": [
            "bilkent üniversitesi", "bilkent universitesi", "bilkent",
            "bilkent university",
        ],
        "organization_name": "Bilkent Üniversitesi",
        "description": "Bilkent Üniversitesi — Ankara.",
        "location": "Bilkent / Ankara 06800",
        "source_url": "https://w3.bilkent.edu.tr/bilkent/contact/",
        "source_name": "Bilkent Üniversitesi iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 290 10 00", 92),
        ],
    },
    {
        "keys": [
            "metu", "orta doğu teknik üniversitesi", "odtü", "odtu",
            "middle east technical university",
        ],
        "organization_name": "Orta Doğu Teknik Üniversitesi (ODTÜ / METU)",
        "description": "ODTÜ — Ankara — öğrenci ve idari iletişim.",
        "location": "Üniversiteler Mah. Dumlupınar Bul. No:1, 06800 Çankaya / Ankara",
        "source_url": "https://www.metu.edu.tr/tr/iletisim",
        "source_name": "ODTÜ resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 210 20 00", 93),
        ],
    },
    {
        "keys": [
            "istanbul teknik üniversitesi", "itu", "itü",
            "istanbul technical university",
        ],
        "organization_name": "İstanbul Teknik Üniversitesi (İTÜ)",
        "description": "İTÜ — Maslak / İstanbul — akademik ve idari iletişim.",
        "location": "Ayazağa Mah. Maslak, 34469 Sarıyer / İstanbul",
        "source_url": "https://www.itu.edu.tr/tr/iletisim",
        "source_name": "İTÜ resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "+90 212 285 30 30", 93),
        ],
    },
    # ── ULAŞIM ────────────────────────────────────────────────────────────────
    {
        "keys": [
            "metro istanbul", "istanbul metro", "iett",
            "iett otobüs", "istanbulkart", "toplu taşıma istanbul",
        ],
        "organization_name": "Metro İstanbul / İETT",
        "description": "İstanbul toplu taşıma — metro, metrobüs, otobüs ve İstanbulkart işlemleri.",
        "location": "İstanbul Büyükşehir Belediyesi, Fatih / İstanbul",
        "source_url": "https://www.iett.istanbul/tr/main/pages/iletisim",
        "source_name": "İETT resmi iletişim sayfası",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "153", 94),
            (LeadContactKind.PHONE, "+90 212 245 07 20", 91),
        ],
    },
    {
        "keys": [
            "ego ankara", "ego genel müdürlüğü", "ankara metro",
            "ankaray", "ankara toplu taşıma",
        ],
        "organization_name": "EGO Genel Müdürlüğü (Ankara)",
        "description": "EGO — Ankara toplu taşıma, metro, otobüs ve AŞTİ işlemleri.",
        "location": "Hipodrom Cad. No:5, 06330 Altındağ / Ankara",
        "source_url": "https://www.ego.gov.tr/tr/icerik/113/iletisim",
        "source_name": "EGO Ankara iletişim sayfası",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 312 384 00 00", 92),
        ],
    },
]


def _normalize_lookup_text(value: str) -> str:
    return (
        value.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def _score_match(haystack: str, keys: list[str]) -> int:
    """Return best word-overlap score (0-100) between haystack and any key."""
    hay_words = set(haystack.split())
    best = 0
    for key in keys:
        key_words = set(key.split())
        if not key_words:
            continue
        overlap = len(hay_words & key_words)
        score = int(overlap / len(key_words) * 100)
        if score > best:
            best = score
    return best


class ManualConnector(IntelligenceConnector):
    source_kind = IntelligenceSourceKind.MANUAL

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        text = seed_text or query
        contacts = extract_contacts(text)
        return [
            ConnectorLead(
                organization_name=query.strip()[:200],
                description=text[:500],
                location=target_location,
                source_url=None,
                source_kind=self.source_kind,
                confidence=75 if contacts else 45,
                consent_basis="user_provided_or_public_business_listing",
                provenance={"mode": "manual_parse", "contact_count": len(contacts)},
                contacts=contacts[:max_results],
            )
        ]


class WebsiteConnector(IntelligenceConnector):
    source_kind = IntelligenceSourceKind.WEBSITE

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        haystack = _normalize_lookup_text(f"{query} {target_location or ''}")
        # Score every entry and pick the best match above threshold
        best_score = 0
        best_item = None
        for item in CURATED_PUBLIC_COMPANIES:
            keys = [_normalize_lookup_text(key) for key in item["keys"]]
            # Exact substring match wins immediately
            if any(key in haystack for key in keys):
                score = 100
            else:
                score = _score_match(haystack, keys)
            if score > best_score:
                best_score = score
                best_item = item

        if best_item and best_score >= 40:
            item = best_item
            contacts = [
                ExtractedContact(
                    kind=kind,
                    value=value,
                    normalized_value=normalize_phone(value) if kind == LeadContactKind.PHONE else value.lower(),
                    confidence=confidence,
                )
                for kind, value, confidence in item["contacts"]
            ]
            return [
                ConnectorLead(
                    organization_name=str(item["organization_name"]),
                    description=str(item["description"]),
                    location=str(item["location"]),
                    source_url=str(item["source_url"]),
                    source_kind=self.source_kind,
                    confidence=int(item["confidence"]),
                    consent_basis="public_business_listing",
                    provenance={
                        "mode": "curated_website_lookup",
                        "matched": True,
                        "match_score": best_score,
                        "source_name": item["source_name"],
                        "source_url": item["source_url"],
                    },
                    contacts=contacts,
                )
            ][:max_results]

        return [
            ConnectorLead(
                organization_name=query.strip()[:200],
                description="No approved public source match is configured for this query yet.",
                location=target_location,
                source_url=None,
                source_kind=self.source_kind,
                confidence=20,
                consent_basis="public_business_listing",
                provenance={"mode": "curated_website_lookup", "matched": False},
                contacts=[],
            )
        ][:max_results]


class GooglePlacesConnector(IntelligenceConnector):
    source_kind = IntelligenceSourceKind.GOOGLE_PLACES
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    field_mask = ",".join(
        [
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.internationalPhoneNumber",
            "places.nationalPhoneNumber",
            "places.websiteUri",
            "places.googleMapsUri",
            "places.types",
        ]
    )

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        settings = get_settings()
        search_query = f"{query} {target_location or ''}".strip()
        encoded = quote_plus(search_query)
        if not settings.google_places_api_key:
            return [
                ConnectorLead(
                    organization_name=query.strip()[:200],
                    description="Google Places API key is not configured. Set GOOGLE_PLACES_API_KEY to enable live discovery.",
                    location=target_location,
                    source_url=f"https://www.google.com/maps/search/{encoded}",
                    source_kind=self.source_kind,
                    confidence=25,
                    consent_basis="public_business_listing",
                    provenance={
                        "mode": "google_places_not_configured",
                        "adapter": "google_places",
                        "search_query": search_query,
                    },
                    contacts=[],
                )
            ][:max_results]
        if not settings.intelligence_external_enabled:
            return [
                ConnectorLead(
                    organization_name=query.strip()[:200],
                    description="External intelligence is disabled by policy. Set INTELLIGENCE_EXTERNAL_ENABLED=true to call Google Places.",
                    location=target_location,
                    source_url=f"https://www.google.com/maps/search/{encoded}",
                    source_kind=self.source_kind,
                    confidence=25,
                    consent_basis="public_business_listing",
                    provenance={
                        "mode": "external_intelligence_disabled",
                        "adapter": "google_places",
                        "search_query": search_query,
                    },
                    contacts=[],
                )
            ][:max_results]

        payload = json.dumps(
            {
                "textQuery": search_query,
                "languageCode": "tr",
                "regionCode": "TR",
                "pageSize": min(max_results, 10),
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": settings.google_places_api_key,
                "X-Goog-FieldMask": self.field_mask,
            },
        )
        try:
            with urlopen(request, timeout=8) as response:  # noqa: S310 - official Google API endpoint
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return [
                ConnectorLead(
                    organization_name=query.strip()[:200],
                    description=f"Google Places request failed with HTTP {exc.code}.",
                    location=target_location,
                    source_url=f"https://www.google.com/maps/search/{encoded}",
                    source_kind=self.source_kind,
                    confidence=20,
                    consent_basis="public_business_listing",
                    provenance={"mode": "google_places_http_error", "status_code": exc.code, "search_query": search_query},
                    contacts=[],
                )
            ]
        except (TimeoutError, URLError) as exc:
            return [
                ConnectorLead(
                    organization_name=query.strip()[:200],
                    description="Google Places request failed due to a network error.",
                    location=target_location,
                    source_url=f"https://www.google.com/maps/search/{encoded}",
                    source_kind=self.source_kind,
                    confidence=20,
                    consent_basis="public_business_listing",
                    provenance={"mode": "google_places_network_error", "error": str(exc), "search_query": search_query},
                    contacts=[],
                )
            ]

        leads: list[ConnectorLead] = []
        for place in data.get("places", [])[:max_results]:
            display_name = (place.get("displayName") or {}).get("text") or query.strip()
            phone = place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber")
            contacts = []
            if phone:
                contacts.append(
                    ExtractedContact(
                        kind=LeadContactKind.PHONE,
                        value=phone,
                        normalized_value=normalize_phone(phone),
                        confidence=90,
                    )
                )
            website = place.get("websiteUri")
            maps_uri = place.get("googleMapsUri")
            source_url = website or maps_uri or f"https://www.google.com/maps/search/{quote_plus(display_name)}"
            leads.append(
                ConnectorLead(
                    organization_name=display_name[:200],
                    description=", ".join(place.get("types", [])[:4]) or "Google Places result",
                    location=place.get("formattedAddress") or target_location,
                    source_url=source_url,
                    source_kind=self.source_kind,
                    confidence=88 if phone else 72,
                    consent_basis="public_business_listing",
                    provenance={
                        "mode": "google_places_text_search",
                        "place_id": place.get("id"),
                        "search_query": search_query,
                        "google_maps_uri": maps_uri,
                        "website_uri": website,
                    },
                    contacts=contacts,
                )
            )
        return leads or [
            ConnectorLead(
                organization_name=query.strip()[:200],
                description="Google Places returned no matching place.",
                location=target_location,
                source_url=f"https://www.google.com/maps/search/{encoded}",
                source_kind=self.source_kind,
                confidence=20,
                consent_basis="public_business_listing",
                provenance={"mode": "google_places_no_results", "search_query": search_query},
                contacts=[],
            )
        ]


class RedditConnector(IntelligenceConnector):
    source_kind = IntelligenceSourceKind.REDDIT_API

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        encoded = quote_plus(query)
        return [
            ConnectorLead(
                organization_name=f"Reddit discussion: {query.strip()[:160]}",
                description="Reddit API connector placeholder. Use official API/OAuth and avoid private or sensitive personal data collection.",
                location=target_location,
                source_url=f"https://www.reddit.com/search/?q={encoded}",
                source_kind=self.source_kind,
                confidence=30,
                consent_basis="public_discussion_reference",
                provenance={"mode": "official_api_required", "adapter": "reddit_api"},
                contacts=[],
            )
        ][:max_results]


class XApiConnector(IntelligenceConnector):
    source_kind = IntelligenceSourceKind.X_API

    def discover(
        self,
        *,
        query: str,
        target_location: str | None,
        max_results: int,
        seed_text: str | None = None,
    ) -> list[ConnectorLead]:
        encoded = quote_plus(query)
        return [
            ConnectorLead(
                organization_name=f"X search: {query.strip()[:180]}",
                description="X API connector placeholder. Use official API access and store only compliant business contact signals.",
                location=target_location,
                source_url=f"https://x.com/search?q={encoded}",
                source_kind=self.source_kind,
                confidence=30,
                consent_basis="public_post_reference",
                provenance={"mode": "official_api_required", "adapter": "x_api"},
                contacts=[],
            )
        ][:max_results]


CONNECTORS: dict[IntelligenceSourceKind, IntelligenceConnector] = {
    IntelligenceSourceKind.MANUAL: ManualConnector(),
    IntelligenceSourceKind.WEBSITE: WebsiteConnector(),
    IntelligenceSourceKind.GOOGLE_PLACES: GooglePlacesConnector(),
    IntelligenceSourceKind.REDDIT_API: RedditConnector(),
    IntelligenceSourceKind.X_API: XApiConnector(),
}


def get_connector(kind: IntelligenceSourceKind) -> IntelligenceConnector | None:
    return CONNECTORS.get(kind)
