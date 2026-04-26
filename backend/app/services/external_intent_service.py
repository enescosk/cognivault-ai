from __future__ import annotations

import re


OUTREACH_ACTION_WORDS = [
    "görüşme",
    "gorusme",
    "arama",
    "ara",
    "telefon",
    "iletişim",
    "iletisim",
    "call",
    "contact",
    "reach",
    "randevu",
    "talep",
    "muayene",
    "doktor",
    "hekim",
    "hastane",
    "danışmanlık",
    "danismanlik",
]


CATEGORY_DEFINITIONS: list[dict] = [
    {
        "category": "göz doktoru",
        "intent": "göz doktoru muayenesi",
        "keywords": ["göz doktoru", "goz doktoru", "göz", "goz", "oftalmoloji", "göz hastalıkları", "goz hastaliklari"],
    },
    {
        "category": "MR görüntüleme",
        "intent": "MR randevusu",
        "keywords": ["mr", "emar", "emar çekimi", "mr çekimi", "mrg", "manyetik rezonans", "radyoloji"],
    },
    {
        "category": "diş doktoru",
        "intent": "diş doktoru muayenesi",
        "keywords": ["diş doktoru", "dis doktoru", "diş", "dis", "dentist", "ortodonti"],
    },
    {
        "category": "fizik tedavi merkezi",
        "intent": "fizik tedavi görüşmesi",
        "keywords": ["fizik tedavi", "fizyoterapi", "ftr"],
    },
    {
        "category": "psikolog",
        "intent": "psikolog görüşmesi",
        "keywords": ["psikolog", "psikiyatri", "terapi"],
    },
    {
        "category": "sağlık merkezi",
        "intent": "sağlık merkezi görüşmesi",
        "keywords": ["sağlık", "saglik", "hastane", "klinik", "doktor", "hekim", "muayene"],
    },
    {
        "category": "veteriner kliniği",
        "intent": "veteriner görüşmesi",
        "keywords": ["veteriner"],
    },
    {
        "category": "spor salonu",
        "intent": "spor salonu görüşmesi",
        "keywords": ["spor salonu", "fitness", "gym", "macfit"],
    },
    {
        "category": "banka",
        "intent": "banka görüşmesi",
        "keywords": ["banka", "kredi", "akbank"],
    },
    {
        "category": "ihracat danışmanlığı",
        "intent": "ihracat danışmanlığı görüşmesi",
        "keywords": ["ihracat", "danışmanlık", "danismanlik"],
    },
]


KNOWN_COMPANIES: list[tuple[str, str]] = [
    (r"\bods(?:\s+consulting(?:\s+group)?)?\b", "ODS Consulting Group"),
    (r"\bmac\s*fit\b|\bmacfit\b", "MACFit"),
    (r"\bak\s*bank\b|\bakbank\b", "Akbank"),
    (r"\bflorence(?:\s+nightingale)?\b", "Ataşehir Florence Nightingale Hastanesi"),
    (r"\bmedistate\b", "Medistate Çekmeköy Hastanesi"),
]

KNOWN_COMPANY_NAMES = {canonical for _, canonical in KNOWN_COMPANIES}


KNOWN_LOCATIONS = [
    "ataşehir",
    "atasehir",
    "kadıköy",
    "kadikoy",
    "üsküdar",
    "uskudar",
    "ümraniye",
    "umraniye",
    "beşiktaş",
    "besiktas",
    "şişli",
    "sisli",
    "bostancı",
    "bostanci",
    "maltepe",
    "kartal",
    "çekmeköy",
    "cekmekoy",
]


def normalize_tr(value: str) -> str:
    return (
        value.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


def canonical_location(value: str) -> str:
    normalized = normalize_tr(value)
    mapping = {
        "atasehir": "Ataşehir",
        "kadikoy": "Kadıköy",
        "uskudar": "Üsküdar",
        "umraniye": "Ümraniye",
        "besiktas": "Beşiktaş",
        "sisli": "Şişli",
        "bostanci": "Bostancı",
        "cekmekoy": "Çekmeköy",
    }
    return mapping.get(normalized, value.strip().title())


def clean_term(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip(" .,!?:;"))
    cleaned = re.sub(r"^(ben|biz|şimdi|simdi|bir|bu|bana|bizim)\s+", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def has_external_action(text: str) -> bool:
    normalized = normalize_tr(text)
    return any(normalize_tr(word) in normalized for word in OUTREACH_ACTION_WORDS)


def infer_company(text: str) -> str | None:
    for pattern, canonical in KNOWN_COMPANIES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return canonical
    match = re.search(r"(.+?)\s+ile\s+.+?(?:görüşme|gorusme|arama|iletişim|iletisim|muayene)", text, flags=re.IGNORECASE)
    if match:
        candidate = clean_term(match.group(1))
        if 2 <= len(candidate) <= 120:
            return candidate
    return None


def infer_location(text: str) -> str | None:
    suffix_match = re.search(
        r"\b([a-zçğıöşüİÇĞÖŞÜ]+)(?:'?(?:deki|daki|teki|taki|de|da|te|ta))\b",
        text,
        flags=re.IGNORECASE,
    )
    if suffix_match:
        candidate = clean_term(suffix_match.group(1))
        known_location_norms = {normalize_tr(item) for item in KNOWN_LOCATIONS}
        if normalize_tr(candidate) in known_location_norms:
            return canonical_location(candidate)

    normalized_text = normalize_tr(text)
    for item in KNOWN_LOCATIONS:
        if normalize_tr(item) in normalized_text:
            return canonical_location(item)
    return None


def infer_category(text: str) -> tuple[str | None, str | None]:
    normalized = normalize_tr(text)
    for definition in CATEGORY_DEFINITIONS:
        if any(normalize_tr(keyword) in normalized for keyword in definition["keywords"]):
            return definition["category"], definition["intent"]
    return None, None


def infer_purpose(text: str, category_intent: str | None) -> str:
    normalized = normalize_tr(text)
    if category_intent and any(keyword in normalized for keyword in ["mr", "emar", "mrg", "manyetik rezonans"]):
        return category_intent
    if "kredi" in normalized:
        return "kredi görüşmesi"
    if "ihracat" in normalized:
        return "ihracat danışmanlığı görüşmesi"
    if "musteri kayit" in normalized or "müşteri kayıt" in text.lower():
        return "müşteri kayıt tekrarı"

    purpose_for_matches = re.findall(r"([^.?!]{3,120}?)\s+(?:için|icin)\b", text, flags=re.IGNORECASE)
    if purpose_for_matches:
        purpose = clean_term(purpose_for_matches[-1])
        if purpose:
            return purpose

    if category_intent and ("muayene" in normalized or "randevu" in normalized or "gorusme" in normalized):
        return category_intent

    purpose_match = re.search(
        r"(?:ile|için|icin|ilgili)\s+(.+?)(?:\s+(?:talep\s+ediyorum|istiyorum|ayarla|başlat|baslat)|$)",
        text,
        flags=re.IGNORECASE,
    )
    if purpose_match:
        purpose = clean_term(purpose_match.group(1))
        if purpose and purpose not in {"ilgili görüşme", "görüşme", "gorusme"}:
            return purpose

    return category_intent or "görüşme talebi"


def build_search_query(company: str | None, category: str | None, location: str | None, purpose: str) -> str:
    parts: list[str] = []
    if company:
        parts.append(company)
    if category and normalize_tr(category) not in normalize_tr(" ".join(parts)):
        parts.append(category)
    if not company and not category:
        parts.append(purpose)
    if location:
        parts.append(location)
    return " ".join(part for part in parts if part).strip()


def extract_external_request_terms(text: str) -> dict | None:
    if not text.strip() or not has_external_action(text):
        return None

    company = infer_company(text)
    location = infer_location(text)
    category, category_intent = infer_category(text)
    if company and company not in KNOWN_COMPANY_NAMES and category and normalize_tr(category) in normalize_tr(company):
        company = None
    if company and company not in KNOWN_COMPANY_NAMES and location and normalize_tr(location) in normalize_tr(company):
        company = None
    purpose = infer_purpose(text, category_intent)
    search_query = build_search_query(company, category, location, purpose)

    if not search_query:
        return None

    return {
        "company": company or category or search_query,
        "category": category,
        "location": location,
        "purpose": purpose,
        "search_query": search_query,
        "entity_type": "company" if company else "category",
        "nlu_provider": "local_rules_v1",
    }
