"""Türkçe diş şikâyeti argo → kanonik terim normalizasyon hattı — İP-1.3.

Ham hasta metnini (argo, yazım varyantları, günlük konuşma dili) ontoloji
anahtar kelimelerine yaklaştıran ön-işleme adımıdır. match_specialty() ve
assess_urgency() doğrudan çağırmak yerine bu modülün triage() fonksiyonunu
kullanın; ham metin korunur, kanonik terimler sona eklenir.

Tasarım kararı: Argo ifadeyi silip yerini kanonik terimle doldurmak yerine
orijinal metnin sonuna terimler ekliyoruz. Böylece:
  - Orijinal hasta ifadesi audit izinde kaybolmaz.
  - Birden fazla kural aynı metne eşleşebilir.
  - Ontoloji kuralları değişse bile ham metin saklanmış olur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.clinical.ontology import (
    SpecialtyMatch,
    UrgencyLevel,
    assess_urgency,
    match_specialty,
    normalize_tr,
)


# ─────────────────────────────────────────────────────────────────────────────
# ARGO → KANONİK TERIM TABLOSU
# Desen normalize_tr() çıktısına uygulanır (küçük harf + ASCII).
# Eşleşen canonical terimler orijinal metnin sonuna eklenir.
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Rule:
    pattern: re.Pattern[str]
    canonical: str


def _r(pattern: str, canonical: str) -> _Rule:
    return _Rule(re.compile(pattern, re.IGNORECASE), canonical)


_RULES: tuple[_Rule, ...] = (
    # ── Endodonti ────────────────────────────────────────────────────────────
    _r(r"sinire\s+gitti|siniri\s+tuttu|siniri\s+pat",           "kanal sinir"),
    _r(r"gece(leri)?\s+(agri|cok\s+agri|zonk|yan)",            "gece agrisi"),
    _r(r"(soguk|sicak|ilik)ta(n)?\s+(zonk|agri|cildiriyor)",   "zonkluyor sinir"),
    _r(r"soguk\s+sicak|sicak\s+soguk|soguga\s+sicaga",          "zonkluyor sinir"),
    _r(r"nabiz\s+gibi\s+at|sekirt|titres",                      "zonkluyor"),
    _r(r"kafama\s+(vurur|vuruyor|gidiyor)\s+gibi",              "zonkluyor"),
    _r(r"kanal\s+tedavisi|kok\s+tedavisi",                      "kanal koke"),
    # apse/irin = diş kaynaklı (endodonti); "diş eti apsesi" perio kuralı ayrı
    _r(r"\bapse|irin\s+(akiyor|var)|apse\s+patlad",            "kanal koke"),

    # ── Restoratif ───────────────────────────────────────────────────────────
    _r(r"curudu|curuk\s+oldu|delik\s+(acildi|var|olustu)",      "dolgu"),
    # tel/braket bağlamındaki kırılmayı dışlar — ortodonti kuralı yakalar
    _r(r"dis\w{0,8}\s+(kirild|yarildi|parcaland|catlad)|parca\w*\s+(kirild|koptu|dustu)|cipti|catlad", "kirik dis"),
    _r(r"(dolgu|plomba|kaplama|porselen)\s+(dustu|cikti|koptu|kaldi)", "dolgu dustu"),
    _r(r"dis\w*\s+rengi\s+degis|karar(di)",                     "dolgu"),

    # ── Periodontoloji ───────────────────────────────────────────────────────
    _r(r"dis\s*etler?(im|i|in)?\s+(sisiy|sald|cekild|kaniy|agriyor)", "dis eti kaniyor"),
    _r(r"firca(lar)?ken\s+(kan\s+)?(geliyor|cikiyor|var)",      "kaniyor dis eti"),
    _r(r"dis(ler)?im?\s+salliy|dis(i)?\s+salliy",               "dis eti"),
    _r(r"dis\s*eti(m|n)?\s+cekild|etler\s+cekild",              "dis eti"),
    _r(r"agiz\s+kokusu|nefes\s+kokuyor|agzim\s+kokuyor|kotu\s+koku", "dis eti"),
    _r(r"dis\s+eti\s+iltiha",                                    "dis eti kaniyor"),

    # ── Pedodonti ────────────────────────────────────────────────────────────
    # İki kanonik token: çocuk bağlamı, sorun-tipinden (örn. "kırık diş") üstün gelsin
    _r(r"oglumun?|kizimin?|yavrumun|cocugun|minigim|minigi|bebegimin", "cocuk cocugum"),
    _r(r"bebek\s+dis(i|ler)|ilk\s+dis",                         "sut disi cocuk"),
    _r(r"sut\s+dis(i|ler)?(\s+dustu|\s+cikti)?",                "sut disi cocuk"),

    # ── Ortodonti ────────────────────────────────────────────────────────────
    # tel + eylem — restoratif "kirik dis" eklemeden sadece "tel braket" yeterli
    _r(r"tel\w*\s+(bozuldu|kirild|dustu|koptu|sanciy)",         "tel braket"),
    _r(r"braket\w*\s+(dustu|koptu|cikti|sanciy)",               "braket"),
    _r(r"invisalign|seffaf\s+(plak|dis\s+teli|aparey)",         "seffaf plak"),

    # ── Çene Cerrahisi ───────────────────────────────────────────────────────
    _r(r"yirmi\s*yas\s*dis(i|im)?|20\s*lik|yirmilik",          "yirmilik gomulu cekim"),
    _r(r"(dis(i|im|ini)?\s+)?cektir(mek|eceğim|ecegim)?|dis\s+aldirt", "cekim"),
    # "çekilecek/çekilsin" = diş çekimi (cene); "diş eti çekilmiş/çekiliyor" perio kuralında ayrı yakalanır
    _r(r"\bcekilecek\b|\bcekilsin\b|cekilmesi\s+gerek",         "cekim"),
    _r(r"gomulu\s+dis|gomuk\s+dis",                              "gomulu cekim"),
    _r(r"agiz\s+acam(iyorum|adim)|agzimi\s+acam",               "cene cerrahisi"),

    # ── İmplantoloji ─────────────────────────────────────────────────────────
    _r(r"implant(im|i)?\s+(agriyor|sisiy|oynuyor|sallaniyor)",  "implant vida"),
    _r(r"vida\s+dis|vida\s+tak(ti|ilan)",                        "vida implant"),

    # ── Estetik ──────────────────────────────────────────────────────────────
    _r(r"gulus\s+tasarimi|estetik\s+dis|porselen\s+kaplama",    "gulus lamina zirkonyum"),
    _r(r"dis(ler)?im\s+sari(ldi)?|dis\s+rengi\s+boz",           "beyazlatma"),

    # ── Medikal Estetik ──────────────────────────────────────────────────────
    _r(r"botoks|dudak\s+dolgusu|mezoterapi|lazer\s+epilasyon",  "botoks dudak dolgusu lazer"),
    _r(r"cilt\s+bakimi|cilt\s+gencl",                           "cilt bakimi"),

    # ── Dermatoloji ──────────────────────────────────────────────────────────
    _r(r"sivilce|akne|egzama|sac\s+dokul|kasin(iy|ti)|ben\s+var\s+buy|bende\s+ben", "akne sivilce egzama"),

    # ── ACİL sinyaller ───────────────────────────────────────────────────────
    _r(r"yuzum\s+(balon|top|gibi\s+sist|cok\s+sist)",           "yuzum sisti"),
    _r(r"kan\s+durmuyor|kan\s+akmaya\s+devam|kan\s+kesmiyor",   "durmayan kanama"),
    _r(r"cene(m|si)?\s+kirild|cene\s+kirigi",                   "cene kirigi"),
    # yüz/çene/ağız bölgesi acil şişlik → maksillofasiyal (çene cerrahisi)
    _r(r"yuzum\s+sisti\s+gozum|gozum\s+kapaniyor|agzimdaki\s+sislik|bogazima\s+vurdu", "yuzum sisti cene kirigi"),
    _r(r"yutam(iy|iy)orum|yutmak(ta)?\s+zorluk",                "yutamiyorum"),
    _r(r"nefes\s+alam(iy|iy)orum|nefes\s+darligi",              "nefes alamiyorum"),
    _r(r"gogsum\s+(agriyor|sikisiyor)|gogus\s+agrisi",           "gogus kalp"),
    _r(r"bayild|bilincin(i|i)\s+kaybet",                         "bayildi"),
)


# ─────────────────────────────────────────────────────────────────────────────
# TEMEL FONKSİYONLAR
# ─────────────────────────────────────────────────────────────────────────────

def expand_complaint(text: str) -> str:
    """Argo şikâyet ifadelerini kanonik terimlerle zenginleştirir.

    Orijinal metni değiştirmez; eşleşen kanonik terimleri sona ekler.
    Sonuç doğrudan match_specialty() ve assess_urgency() fonksiyonlarına
    geçirilebilir.
    """
    normalized = normalize_tr(text)
    expansions: list[str] = []
    for rule in _RULES:
        if rule.pattern.search(normalized):
            expansions.append(rule.canonical)
    if not expansions:
        return text
    return text + " " + " ".join(dict.fromkeys(expansions))  # sıra koruyarak tekrarsız


# ─────────────────────────────────────────────────────────────────────────────
# TRİAJ SARMALAYICI
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TriageResult:
    """Tek şikâyetin komple triyaj sonucu.

    raw_text:       Orijinal hasta girişi (değiştirilmemiş).
    enriched_text:  Kanonik terimler eklenmiş genişletilmiş metin.
    specialty:      Branş eşleme sonucu (ontoloji SpecialtyMatch).
    urgency:        Operasyonel aciliyet seviyesi.
    expansions:     Tetiklenen kanonik terim grupları (audit için).
    """

    raw_text: str
    enriched_text: str
    specialty: SpecialtyMatch
    urgency: UrgencyLevel
    expansions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def specialty_code(self) -> str:
        return self.specialty.specialty.code

    @property
    def requires_escalation(self) -> bool:
        return self.urgency.requires_human_escalation


def triage(text: str) -> TriageResult:
    """Ham şikâyet metninden tam triyaj sonucu üretir.

    Adımlar:
      1. expand_complaint() → argo genişletme
      2. match_specialty()  → branş eşleme
      3. assess_urgency()   → aciliyet değerlendirme
    """
    normalized = normalize_tr(text)
    expansions: list[str] = []
    for rule in _RULES:
        if rule.pattern.search(normalized):
            expansions.append(rule.canonical)

    enriched = text + (" " + " ".join(dict.fromkeys(expansions)) if expansions else "")
    specialty = match_specialty(enriched)
    urgency = assess_urgency(enriched)

    return TriageResult(
        raw_text=text,
        enriched_text=enriched,
        specialty=specialty,
        urgency=urgency,
        expansions=tuple(dict.fromkeys(expansions)),
    )
