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
    {
        "keys": ["ods", "ods consulting", "ods consulting group"],
        "organization_name": "ODS Consulting Group",
        "description": "Uluslararası iş geliştirme ve ihracat danışmanlığı dahil yönetim danışmanlığı hizmetleri.",
        "location": "Kızılırmak Mah. Dumlupınar Bul. Next Level A Blok No: 3/100, 101, 102, 103, 06520 Çankaya, Ankara / Türkiye",
        "source_url": "https://ods.consulting/contact/",
        "source_name": "ODS Consulting contact page",
        "confidence": 92,
        "contacts": [
            (LeadContactKind.PHONE, "+90 531 637 74 89", 92),
            (LeadContactKind.EMAIL, "contact@ods.consulting", 88),
        ],
    },
    {
        "keys": ["macfit", "mac fit", "macfit ümraniye", "macfit umraniye", "macfit buyaka"],
        "organization_name": "MACFit Buyaka",
        "description": "Ümraniye Buyaka AVM'de bulunan MACFit spor salonu.",
        "location": "Buyaka AVM FSM Mah. Balkan Cad. No:56 Ümraniye / İstanbul",
        "source_url": "https://www.macfit.com/kulupler/istanbul/macfit-buyaka/",
        "source_name": "MACFit Buyaka official club page",
        "confidence": 93,
        "contacts": [
            (LeadContactKind.PHONE, "0850 241 30 00", 93),
        ],
    },
    {
        "keys": ["akbank", "ak bank"],
        "organization_name": "Akbank",
        "description": "Akbank resmi müşteri iletişim merkezi.",
        "location": "Akbank Müşteri İletişim Merkezi",
        "source_url": "https://www.akbank.com/tr-tr/genel/Sayfalar/musteri-iletisim-merkezi.aspx",
        "source_name": "Akbank official customer contact page",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 25 25", 94),
            (LeadContactKind.PHONE, "0850 222 25 25", 94),
        ],
    },
    {
        "keys": [
            "florence",
            "florence nightingale",
            "ataşehir florence",
            "atasehir florence",
            "ataşehir florence nightingale",
            "atasehir florence nightingale",
        ],
        "organization_name": "Ataşehir Florence Nightingale Hastanesi",
        "description": "Grup Florence Nightingale Ataşehir hastanesi.",
        "location": "Küçükbakkalköy, Işıklar Cd. No:35/A, 34750 Ataşehir / İstanbul",
        "source_url": "https://groupflorence.com/en/why-choose-us/hospitals-opcs/atasehir-florence-nightingale-hospital/",
        "source_name": "Group Florence Nightingale official hospital page",
        "confidence": 91,
        "contacts": [
            (LeadContactKind.PHONE, "+90 850 711 60 60", 91),
        ],
    },
    {
        "keys": [
            "medistate",
            "medistate çekmeköy",
            "medistate cekmekoy",
            "özel medistate çekmeköy hastanesi",
            "ozel medistate cekmekoy hastanesi",
        ],
        "organization_name": "Medistate Çekmeköy Hastanesi",
        "description": "Özel Medistate Çekmeköy Hastanesi; radyoloji ve MR dahil sağlık hizmetleri sunan hastane.",
        "location": "Merkez, Erenler Cd No:16, 34782 Çekmeköy / İstanbul",
        "source_url": "https://www.medistate.com.tr/hastanelerimiz/cekmekoy-hastanesi",
        "source_name": "Medistate official Çekmeköy hospital page",
        "confidence": 94,
        "contacts": [
            (LeadContactKind.PHONE, "444 44 13", 94),
            (LeadContactKind.EMAIL, "bilgi@medistate.com.tr", 86),
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
        for item in CURATED_PUBLIC_COMPANIES:
            keys = [_normalize_lookup_text(key) for key in item["keys"]]
            if any(key in haystack for key in keys):
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
