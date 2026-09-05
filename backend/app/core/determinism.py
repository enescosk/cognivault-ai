"""Platformlar arası kararlı kanıt artefaktları.

Kanıt panolarımız (`data/*.json`) repoya **commit'lenir** ve testler bunları
üreticinin çıktısıyla **birebir** karşılaştırır (bayatlama kapısı). Bu kapı
ancak üretici her makinede aynı JSON'u üretirse çalışır.

Tamsayı sayaçlar ve oranlar zaten kararlı; sorun `math` tabanlı ara değerlerden
(exp/log/pow) geçen kayan noktalı metrikler: libm implementasyonu platforma göre
son bitte farklı sonuç verebiliyor. Örnek — aynı korpus, aynı seed:

    macOS arm64 : golden_ece = 0.24808362369337983
    Linux x86-64: golden_ece = 0.24808362369337997

Fark 1e-16 mertebesinde, yani metriğin anlamı açısından SIFIR (ECE hedefi 0,05
ve raporlarda 4 basamak gösteriliyor) — ama `==` karşılaştırmasını kırıyor ve
CI'ı kırmızıya çeviriyor.

Çözüm: artefakta girmeden önce her kayan noktalı değeri sabit hassasiyete
yuvarla. 9 basamak, raporlanan hassasiyetin (4) çok üzerinde; kapı eşiklerini
(ECE<0,05, recall=1,0, AUC≥0,75) etkileyecek bir kayıp yok.
"""
from __future__ import annotations

ARTIFACT_FLOAT_DIGITS = 9


def stabilize_floats(value, digits: int = ARTIFACT_FLOAT_DIGITS):
    """JSON-hazır bir yapıdaki tüm float'ları yuvarlayarak platformdan bağımsız kılar.

    dict/list/tuple içinde özyinelemeli çalışır. `bool` bilerek dışarıda
    bırakılır (Python'da `bool` bir `int` alt tipidir, sayı gibi işlenmemeli).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: stabilize_floats(v, digits) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [stabilize_floats(v, digits) for v in value]
    return value
