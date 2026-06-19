"""Elle küratörlü "golden" değerlendirme seti — İP-1.2.

Şablon üreticisinden (build.py) kasıtlı olarak DAHA ZOR vakalar: yazım/aksan
sapması, kod-değiştirme (İngilizce kelimeler), branşlar arası belirsizlik,
anahtar-kelime içermeyen parafraz ve sıra dışı ifade edilmiş acil tablolar.
Yönlendiricinin (İP-1.4) ve kalibrasyonun (İP-1.5) gerçek dünyaya
dayanıklılığını ölçmek için kullanılır.

Etiketler küratör niyetidir (yer-doğruluğu). Çalıştırma:
    python -m app.clinical.corpus.build_golden
"""

from __future__ import annotations

from app.clinical.corpus.schema import (
    CorpusEntry,
    corpus_data_dir,
    save_corpus,
    validate_entry,
)

# (text, specialty_code, urgency, channel)
GOLDEN_CASES: tuple[tuple[str, str, str, str], ...] = (
    # — Aksan/yazım sapması (diakritik yok) —
    ("dis kontrolu icin ne zaman gelebilirim", "genel_dis", "routine", "phone"),
    ("dis etlerim cekiliyor sanki bi bakilsin", "periodontoloji", "routine", "whatsapp"),
    ("oglumun sut disi sallaniyor cekilsin mi", "pedodonti", "routine", "whatsapp"),
    ("soguk su icince disim feci sizliyor", "endodonti", "priority", "whatsapp"),
    ("dis fircalarken kan tukuruyorum surekli", "periodontoloji", "priority", "phone"),

    # — Kod-değiştirme (İngilizce terimler) —
    ("checkup yaptırmak istiyorum dişlerime genel", "genel_dis", "routine", "web"),
    ("gülüşümü düzelttirmek istiyorum hollywood smile gibi", "estetik_dis", "routine", "web"),
    ("invisalign var mı sizde şeffaf plak", "ortodonti", "routine", "web"),
    ("gece dişim o kadar ağrıyor ki painkiller bile kesmiyor", "endodonti", "priority", "whatsapp"),
    ("kırışıklıklarım için botox düşünüyorum bilgi alabilir miyim", "medikal_estetik", "routine", "web"),

    # — Anahtar kelime içermeyen parafraz (zor eşleme) —
    ("kayıp dişim için kalıcı bir çözüm istiyorum vidalı olan", "implantoloji", "routine", "web"),
    ("dişimde kara bir nokta var çürük olabilir mi", "restoratif", "routine", "whatsapp"),
    ("ağzımda kötü bir koku var neden olur acaba", "periodontoloji", "routine", "phone"),
    ("eski gümüş dolgumu beyazıyla değiştirmek istiyorum", "restoratif", "routine", "web"),
    ("kahve içtikçe dişlerim sarardı parlatmak istiyorum", "estetik_dis", "routine", "web"),
    ("kanal tedavim yarım kalmıştı tamamlatmak istiyorum", "endodonti", "routine", "phone"),

    # — Branşlar arası belirsizlik (en savunulabilir etiket) —
    ("ön dişim kırıldı görüntü çok kötü düzeltilsin", "restoratif", "priority", "whatsapp"),
    ("dişim çekildi yerine ne yaptırabilirim kalıcı olsun", "implantoloji", "routine", "web"),
    ("kızımın dişleri çapraşık çıkıyor tel gerekir mi", "ortodonti", "routine", "whatsapp"),
    ("gömülü yirmilik için ameliyat gerekiyormuş", "cene_cerrahisi", "routine", "phone"),

    # — Komşu branşlar (dermatoloji / medikal estetik) —
    ("yüzümdeki sivilceler bir türlü geçmiyor ne önerirsiniz", "dermatoloji", "routine", "web"),
    ("dudak dolgusu yaptırdım aşırı şişti morardı normal mi", "medikal_estetik", "priority", "whatsapp"),
    ("yüzümde aniden büyüyen kızarık bir şişlik var", "dermatoloji", "priority", "phone"),

    # — Öncelikli (ağrı/şişlik) sıra dışı ifade —
    ("20lik azı sürerken çenem kilitlendi açamıyorum acıyor", "cene_cerrahisi", "priority", "whatsapp"),
    ("dolgu düştü altındaki diş zonklayıp duruyor", "restoratif", "priority", "phone"),
    ("telin ucu battı yanağımı kanattı çok acıyor", "ortodonti", "priority", "whatsapp"),
    ("implant yaptırdığım bölge şişti irin var gibi", "implantoloji", "priority", "phone"),
    ("çocuğun dişi çok ağrıyor gece boyu ağladı", "pedodonti", "priority", "whatsapp"),
    ("bebeğimin diş eti şişmiş huzursuz emmiyor", "pedodonti", "priority", "phone"),

    # — Acil (sıra dışı/parafraz ifade) —
    ("yüzümün yarısı şişti nefes almakta zorlanıyorum", "genel_dis", "emergency", "phone"),
    ("diş çektirdim iki saattir kan durmuyor başım dönüyor", "periodontoloji", "emergency", "phone"),
    ("kaza geçirdim çenem kırık dişlerim de kırıldı", "cene_cerrahisi", "emergency", "phone"),
    ("apse patladı irin akıyor yutkunamıyorum", "endodonti", "emergency", "whatsapp"),
    ("ağzıma sert darbe aldım çok kanıyor sersemledim", "genel_dis", "emergency", "phone"),
    ("diş eti apsem büyüdü yüzüm şişti gözüm kapanıyor", "endodonti", "emergency", "whatsapp"),
)


def build_golden() -> list[CorpusEntry]:
    """Golden vakaları doğrulanmış CorpusEntry listesine çevirir."""
    entries: list[CorpusEntry] = []
    for index, (text, code, urgency, channel) in enumerate(GOLDEN_CASES, start=1):
        entry = CorpusEntry(
            id=f"gold-{index:04d}",
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
        entries.append(entry)
    return entries


def main() -> None:
    entries = build_golden()
    out_path = corpus_data_dir() / "golden.jsonl"
    count = save_corpus(entries, out_path)
    print(f"Golden set: {count} vaka → {out_path}")


if __name__ == "__main__":
    main()
