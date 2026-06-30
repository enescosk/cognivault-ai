"""Adversarial acil senaryo seti — İP-1.7.

Acil tabloların sıra dışı, argo, kod-değiştirmeli ve parafraz ifadeleri.
Amaç: aciliyet motorunun (`assess_urgency` + normalizer genişletmesi)
acil-recall'ünü (kaçan acil ≈ 0) stres altında doğrulamak.

Set iki bölümden oluşur:
  * EMERGENCY_CASES — gerçek aciller; tamamı EMERGENCY tespit edilmeli (recall).
  * HARD_NEGATIVES  — acile benzeyen ama acil OLMAYAN (rutin/öncelik) tuzaklar;
                      acile kaçmamalı (precision koruması).

Etiketler küratör niyetidir (yer-doğruluğu). Branş etiketi acil triyajda ikincil
olduğundan savunulabilir en yakın branş seçilir. Çalıştırma:
    python -m app.clinical.corpus.build_emergency
"""

from __future__ import annotations

from app.clinical.corpus.schema import (
    CorpusEntry,
    corpus_data_dir,
    save_corpus,
    validate_entry,
)

# (text, specialty_code, channel) — hepsi urgency="emergency"
EMERGENCY_CASES: tuple[tuple[str, str, str], ...] = (
    # — Kontrolsüz kanama —
    ("çekimden sonra kanama bir türlü dinmedi", "cene_cerrahisi", "phone"),
    ("iki saat oldu kanı durduramıyorum", "cene_cerrahisi", "phone"),
    ("ağzım sürekli kan doluyor tükürdükçe doluyor", "periodontoloji", "phone"),
    ("diş etinden gelen kanama hiç kesilmiyor", "periodontoloji", "whatsapp"),
    ("o kadar çok kan kaybediyorum ki halsizim", "cene_cerrahisi", "phone"),
    ("operasyondan sonra kanama akmaya devam ediyor", "cene_cerrahisi", "phone"),
    ("hocam kan durmak bilmiyor napacağımı şaşırdım", "cene_cerrahisi", "whatsapp"),
    ("valla ağzımdan kan boşalıyor durduramadım", "periodontoloji", "phone"),
    # — Havayolu / şişlik —
    ("yüzüm aşırı şişti nefes almakta zorlanıyorum", "cene_cerrahisi", "phone"),
    ("boğazım şişiyor yutkunamıyorum", "endodonti", "phone"),
    ("dilim şişti soluk alamıyorum", "genel_dis", "phone"),
    ("gözüm kapanacak kadar şişti yüzüm", "cene_cerrahisi", "whatsapp"),
    ("şişlik boğazıma indi nefessiz kaldım", "endodonti", "phone"),
    ("boynum şişti nefes daralıyor", "cene_cerrahisi", "phone"),
    # — Travma / çene kırığı —
    ("trafik kazası geçirdim çenem kırık", "cene_cerrahisi", "phone"),
    ("düştüm çenem kırıldı kapanmıyor", "cene_cerrahisi", "phone"),
    ("ağzıma sert bir cisim çarptı dişlerim kırıldı", "cene_cerrahisi", "phone"),
    ("yumruk yedim çenem oynamıyor", "cene_cerrahisi", "whatsapp"),
    ("merdivenden düştüm çeneme darbe aldım", "cene_cerrahisi", "phone"),
    ("yüzüme top çarptı dişim yerinden çıktı", "cene_cerrahisi", "whatsapp"),
    # — Bilinç / sistemik —
    ("diş ağrısından neredeyse bayılacağım", "endodonti", "phone"),
    ("başım döndü sersemledim ayakta duramıyorum", "genel_dis", "phone"),
    ("göğsüm sıkışıyor nefes darlığım var", "genel_dis", "phone"),
    ("gözlerim karardı fenalık geçiriyorum", "genel_dis", "phone"),
    ("kalbim hızlı çarpıyor göğsüm ağrıyor", "genel_dis", "phone"),
    # — Apse + sistemik —
    ("apse patladı yutkunamıyorum ateşim çıktı", "endodonti", "whatsapp"),
    ("yüzüm şişti gözüm kapandı irin akıyor", "endodonti", "whatsapp"),
    ("diş apsem yüzüme yayıldı boğazım şişti", "endodonti", "phone"),
    # — Kısa / panik ifade —
    ("112 lazım mı çenem kırıldı kanıyor", "cene_cerrahisi", "phone"),
    ("acil yardım nefes alamıyorum yüzüm şişti", "genel_dis", "phone"),
)

# (text, specialty_code, urgency, channel) — acile benzeyen tuzaklar
HARD_NEGATIVES: tuple[tuple[str, str, str, str], ...] = (
    ("nefesim kötü kokuyor ağız kokusu var", "periodontoloji", "routine", "web"),
    ("ağız kokum geçmiyor nefesim fena", "periodontoloji", "routine", "phone"),
    ("diş etim fırçalarken biraz kanıyor", "periodontoloji", "priority", "whatsapp"),
    ("çekim oldu hafif kanama oldu normal mi", "cene_cerrahisi", "priority", "phone"),
    ("dişim zonkluyor ağrı durmuyor", "endodonti", "priority", "whatsapp"),
    ("yüzümde sivilce şişliği var geçmiyor", "dermatoloji", "routine", "web"),
    ("kanamam durdu artık iyiyim teşekkürler", "cene_cerrahisi", "routine", "whatsapp"),
    ("nefes egzersizi diş hekimi korkusu için işe yarar mı", "genel_dis", "routine", "web"),
    ("göğüs hizasına kadar önlük veriyor musunuz çekimde", "genel_dis", "routine", "web"),
    ("kalp ilacı kullanıyorum çekim olur mu", "cene_cerrahisi", "routine", "phone"),
)


def build_emergency() -> list[CorpusEntry]:
    """Adversarial acil + hard-negative vakaları doğrulanmış kayıtlara çevirir."""
    entries: list[CorpusEntry] = []
    index = 0
    for text, code, channel in EMERGENCY_CASES:
        index += 1
        entries.append(_entry(index, text, code, "emergency", channel))
    for text, code, urgency, channel in HARD_NEGATIVES:
        index += 1
        entries.append(_entry(index, text, code, urgency, channel))
    return entries


def _entry(index: int, text: str, code: str, urgency: str, channel: str) -> CorpusEntry:
    entry = CorpusEntry(
        id=f"emg-{index:04d}",
        text=text,
        specialty_code=code,
        urgency=urgency,
        channel=channel,
        source="golden_curated",
        lang="tr",
    )
    errors = validate_entry(entry)
    if errors:  # pragma: no cover - küratör hatası
        raise ValueError(f"{entry.id} doğrulama hatası: {errors} — {text!r}")
    return entry


def main() -> None:
    entries = build_emergency()
    out_path = corpus_data_dir() / "emergency_adversarial.jsonl"
    count = save_corpus(entries, out_path)
    n_emg = sum(1 for e in entries if e.urgency == "emergency")
    print(f"Adversarial acil seti: {count} vaka ({n_emg} acil + {count - n_emg} tuzak) → {out_path}")


if __name__ == "__main__":
    main()
