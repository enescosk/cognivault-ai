"""Diş hekimliği triyaj ontolojisi — branş ve aciliyet taksonomisi.

İP-1.1 çıktısı. Bu modül, triyaj yönlendiricisinin (İP-1.4) ve kalibrasyon
çalışmasının (İP-1.5) üstüne kurulacağı **tek doğru kaynaktır**. Branş ve
aciliyet bilgisi başka hiçbir yerde elle tanımlanmaz; tüm servisler buradan
okur.

Şema, klinik danışma kurulu hekimlerinin (İstanbul Üniversitesi / Medipol)
gözden geçirip onaylaması için bilinçli olarak sade ve okunur tutulmuştur:
her branş bir kod, kanonik Türkçe ad, eş anlamlı/argo anahtar kelime kümesi
ve yönlendirme gerekçesi taşır.

NON-SaMD İLKESİ: Aciliyet bir klinik şiddet/teşhis değerlendirmesi DEĞİLDİR.
Yalnızca operasyonel bir sinyaldir — hekime yükseltme ve randevu
önceliklendirme için kullanılır. Teşhis veya tedavi talimatı üretmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ─────────────────────────────────────────────────────────────────────────────
# Türkçe normalizasyon — argo/günlük şikâyeti ASCII-kanonik forma indirger.
# Ontoloji eşlemesi ve aşağı akış NLU bu fonksiyonu paylaşır.
# ─────────────────────────────────────────────────────────────────────────────

def normalize_tr(text: str) -> str:
    """Türkçe metni küçük harfe çevirip aksanlı karakterleri ASCII'ye indirger."""
    return (
        text.lower()
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
    )


# ─────────────────────────────────────────────────────────────────────────────
# ACİLİYET (URGENCY) TAKSONOMİSİ
# Operasyonel öncelik sinyali — klinik teşhis değil.
# ─────────────────────────────────────────────────────────────────────────────

class UrgencyLevel(str, Enum):
    """Operasyonel aciliyet seviyeleri (artan öncelik).

    Değerler eski string sözleşmesiyle uyumludur ("routine"/"priority"/
    "emergency") — aşağı akış karşılaştırmaları kırılmaz.
    """

    ROUTINE = "routine"      # Normal randevu akışı.
    PRIORITY = "priority"    # İvedi/aynı-gün slot; hekim önceliği.
    EMERGENCY = "emergency"  # Derhal insana/112 yükselt; otomatik randevu yok.

    @property
    def rank(self) -> int:
        """Sıralama için sayısal öncelik (yüksek = daha acil)."""
        return _URGENCY_RANK[self]

    @property
    def requires_human_escalation(self) -> bool:
        """Bu seviye her zaman insana yükseltilmeli mi?"""
        return self in (UrgencyLevel.EMERGENCY, UrgencyLevel.PRIORITY)


_URGENCY_RANK: dict[UrgencyLevel, int] = {
    UrgencyLevel.ROUTINE: 0,
    UrgencyLevel.PRIORITY: 1,
    UrgencyLevel.EMERGENCY: 2,
}

# EMERGENCY: her koşulda 112/insan yükseltmesi gerektiren ifadeler.
EMERGENCY_KEYWORDS: frozenset[str] = frozenset({
    "nefes", "nefes alamiyorum", "nefes alamıyorum",
    "gogus", "göğüs", "kalp",
    "bayildi", "bayıldı",
    "kontrol edilemeyen kanama", "durmayan kanama",
    "cene kirigi", "çene kırığı",
    "yuzum sisti", "yüzüm şişti",
    "yutamiyorum", "yutamıyorum",
    "112",
})

# PRIORITY: acil değil ama ivedi/öncelikli slot gerektiren şikâyet işaretleri.
PRIORITY_KEYWORDS: frozenset[str] = frozenset({
    "agri", "ağrı", "agriyor", "ağrıyor",
    "zonkluyor", "sisti", "şişti", "kanama",
})


def assess_urgency(text: str) -> UrgencyLevel:
    """Şikâyet metninden operasyonel aciliyet seviyesini çıkarır.

    Önce EMERGENCY taranır (en yüksek öncelik), sonra PRIORITY; hiçbiri
    yoksa ROUTINE döner.
    """
    normalized = normalize_tr(text)
    if any(normalize_tr(term) in normalized for term in EMERGENCY_KEYWORDS):
        return UrgencyLevel.EMERGENCY
    if any(normalize_tr(term) in normalized for term in PRIORITY_KEYWORDS):
        return UrgencyLevel.PRIORITY
    return UrgencyLevel.ROUTINE


# ─────────────────────────────────────────────────────────────────────────────
# BRANŞ (SPECIALTY) TAKSONOMİSİ
# ─────────────────────────────────────────────────────────────────────────────

class SpecialtyScope(str, Enum):
    """Branşın klinik kapsamı.

    DENTAL: diş hekimliği çekirdek branşları (BiGG Ar-Ge odağı).
    ADJACENT: çok-disiplinli kliniklerde bulunan komşu branşlar (estetik vb.).
    """

    DENTAL = "dental"
    ADJACENT = "adjacent"


@dataclass(frozen=True)
class DentalSpecialty:
    """Tek bir branşın ontoloji kaydı.

    code:          Kararlı kimlik (DB/log/metrik anahtarı olarak kullanılır).
    display_tr:    Kanonik Türkçe branş adı (hekim onayına tabi).
    keywords:      Eş anlamlı/argo şikâyet ifadeleri (normalize edilmemiş hâl).
    routing_reason: Yönlendirme gerekçesi (denetim izi için makine-okunur etiket).
    scope:         DENTAL veya ADJACENT.
    """

    code: str
    display_tr: str
    keywords: frozenset[str]
    routing_reason: str
    scope: SpecialtyScope = SpecialtyScope.DENTAL


# Varsayılan branş — hiçbir kural eşleşmezse genel diş hekimliğine yönlendirilir.
GENERAL_SPECIALTY = DentalSpecialty(
    code="genel_dis",
    display_tr="Genel Diş Hekimliği",
    keywords=frozenset(),
    routing_reason="general_dental_intake",
    scope=SpecialtyScope.DENTAL,
)


# Branş kayıtları. Sıra önceliklidir: ilk eşleşen branş kazanır.
SPECIALTY_REGISTRY: tuple[DentalSpecialty, ...] = (
    DentalSpecialty(
        code="restoratif",
        display_tr="Restoratif Diş Tedavisi",
        keywords=frozenset({"dolgu", "dolgum", "dolgu düştü", "dolgu dustu", "kırık diş", "kirik dis"}),
        routing_reason="restorative_dental",
    ),
    DentalSpecialty(
        code="endodonti",
        display_tr="Endodonti",
        keywords=frozenset({"zonkluyor", "kanal", "gece ağrısı", "gece agrisi", "sinir", "köke", "koke"}),
        routing_reason="dis_pain_root_canal",
    ),
    DentalSpecialty(
        code="periodontoloji",
        display_tr="Periodontoloji",
        keywords=frozenset({
            "diş eti", "dis eti", "diş etler", "dis etler", "diş etim", "dis etim",
            "kanıyor", "kaniyor", "kanama",
        }),
        routing_reason="gum_bleeding",
    ),
    DentalSpecialty(
        code="pedodonti",
        display_tr="Pedodonti",
        keywords=frozenset({"çocuğum", "cocugum", "çocuk", "cocuk", "süt dişi", "sut disi"}),
        routing_reason="pediatric_dental",
    ),
    DentalSpecialty(
        code="ortodonti",
        display_tr="Ortodonti",
        keywords=frozenset({"tel", "braket", "ortodonti", "plak", "şeffaf plak", "seffaf plak"}),
        routing_reason="orthodontics",
    ),
    DentalSpecialty(
        code="implantoloji",
        display_tr="İmplantoloji",
        keywords=frozenset({"implant", "vida", "kemik tozu"}),
        routing_reason="implant_followup",
    ),
    DentalSpecialty(
        code="cene_cerrahisi",
        display_tr="Ağız, Diş ve Çene Cerrahisi",
        keywords=frozenset({
            "çekim", "cekim", "20lik", "yirmilik", "gömülü", "gomulu", "çene kırığı", "cene kirigi",
        }),
        routing_reason="oral_surgery",
    ),
    DentalSpecialty(
        code="estetik_dis",
        display_tr="Estetik Diş Hekimliği",
        keywords=frozenset({"beyazlatma", "gülüş", "gulus", "lamina", "zirkonyum"}),
        routing_reason="cosmetic_dentistry",
    ),
    DentalSpecialty(
        code="dermatoloji",
        display_tr="Dermatoloji",
        # "ben" (zamir) ile çakıştığı için bare "ben" yerine bağlamlı normalizer kuralı kullanılır.
        keywords=frozenset({"akne", "sivilce", "leke", "egzama", "saç dökülmesi", "sac dokulmesi"}),
        routing_reason="dermatology",
        scope=SpecialtyScope.ADJACENT,
    ),
    DentalSpecialty(
        code="medikal_estetik",
        display_tr="Medikal Estetik",
        keywords=frozenset({"botoks", "dudak dolgusu", "mezoterapi", "lazer", "cilt bakımı", "cilt bakimi"}),
        routing_reason="medical_aesthetic",
        scope=SpecialtyScope.ADJACENT,
    ),
)

# Kod → branş hızlı erişim haritası.
SPECIALTY_BY_CODE: dict[str, DentalSpecialty] = {
    spec.code: spec for spec in (GENERAL_SPECIALTY, *SPECIALTY_REGISTRY)
}


@dataclass(frozen=True)
class SpecialtyMatch:
    """Branş eşleme sonucu — eşleşen branş ve tetikleyen anahtar kelimeler."""

    specialty: DentalSpecialty
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_default(self) -> bool:
        """Genel diş hekimliğine (hiçbir kural eşleşmeden) düşüldü mü?"""
        return self.specialty.code == GENERAL_SPECIALTY.code


@dataclass(frozen=True)
class ScoredSpecialty:
    """Bir branşın bir metne karşı sözlüksel eşleşme skoru.

    match_count:  Tekilleştirilmiş eşleşen anahtar kelime sayısı.
    match_length: Eşleşen kanonik kelimelerin toplam karakter uzunluğu.
    """

    specialty: DentalSpecialty
    matched_keywords: tuple[str, ...]
    match_count: int
    match_length: int

    @property
    def score(self) -> tuple[int, int]:
        return (self.match_count, self.match_length)


def rank_specialties(text: str) -> list[ScoredSpecialty]:
    """Eşleşen tüm branşları skora göre azalan sırada döndürür.

    Skor = (tekil eşleşme sayısı, toplam eşleşen uzunluk). Hiç eşleşme yoksa
    boş liste döner. Beraberlikte SPECIALTY_REGISTRY sırası korunur (DENTAL
    branşlar ADJACENT'tan önce; Python'ın kararlı sıralaması bunu garanti eder).

    Hem `match_specialty()` (en iyi eşleşme) hem de kalibrasyon güven sinyali
    (İP-1.5; en iyi ile rakibi arasındaki marj) bu tek skorlama kaynağını kullanır.
    """
    normalized = normalize_tr(text)
    scored: list[ScoredSpecialty] = []
    for spec in SPECIALTY_REGISTRY:
        hits = tuple(kw for kw in spec.keywords if normalize_tr(kw) in normalized)
        if not hits:
            continue
        # Normalize edilmiş forma göre tekilleştir — "diş eti" ve "dis eti" gibi
        # aynı kanonik forma inen varyantlar skoru şişirmesin.
        distinct = {normalize_tr(kw) for kw in hits}
        scored.append(
            ScoredSpecialty(
                specialty=spec,
                matched_keywords=hits,
                match_count=len(distinct),
                match_length=sum(len(n) for n in distinct),
            )
        )
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def match_specialty(text: str) -> SpecialtyMatch:
    """Şikâyet metnini branşa eşler (skorlama tabanlı).

    En yüksek skorlu branş kazanır. Bu, saf "ilk eşleşen kazanır" mantığının
    aksine, daha uzun/daha spesifik ifadeleri kısa alt-dizi çakışmalarına
    tercih eder — örn. "dudak dolgusu" (medikal estetik) artık "dolgu"
    (restoratif) alt-dizisine kapılmaz.

    Beraberlikte kayıt sırası belirleyicidir (DENTAL branşlar ADJACENT'tan
    önce gelir). Hiçbiri eşleşmezse GENERAL_SPECIALTY döner (is_default=True).
    """
    ranked = rank_specialties(text)
    if not ranked:
        return SpecialtyMatch(specialty=GENERAL_SPECIALTY)
    top = ranked[0]
    return SpecialtyMatch(specialty=top.specialty, matched_keywords=top.matched_keywords)
