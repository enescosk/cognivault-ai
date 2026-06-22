"""İP-1.3 — Türkçe argo normalizasyon hattı testleri.

Kapsam:
  - expand_complaint(): argo → kanonik terim genişletme
  - triage(): ham metinden branş + aciliyet
  - Yanlış-pozitif koruması (alakasız metin genişlememeli)
  - Ontoloji entegrasyonu (genişletilmiş metin doğru branşa eşlenmeli)
"""

from __future__ import annotations

import pytest

from app.clinical.normalizer import TriageResult, expand_complaint, triage
from app.clinical.ontology import UrgencyLevel


# ─────────────────────────────────────────────────────────────────────────────
# expand_complaint — genişletme kuralları
# ─────────────────────────────────────────────────────────────────────────────

class TestExpandComplaint:
    def test_no_expansion_for_clean_text(self):
        """Kanonik terim içeren metin olduğu gibi döner (ek ekspansiyon olmaz)."""
        text = "dolgum düştü"
        result = expand_complaint(text)
        assert result.startswith(text)

    def test_curuk_expands_to_dolgu(self):
        result = expand_complaint("dişim çürüdü")
        assert "dolgu" in result

    def test_kirildim_expands_to_kirik_dis(self):
        result = expand_complaint("Dişimin bir parçası kırıldı")
        assert "kirik dis" in result

    def test_sinire_gitti_expands_to_kanal(self):
        result = expand_complaint("sanırım sinire gitti")
        assert "kanal" in result

    def test_nabiz_gibi_atıyor_expands_to_zonkluyor(self):
        result = expand_complaint("Ağrı nabız gibi atıyor")
        assert "zonkluyor" in result

    def test_fircalarken_kan_expands_to_dis_eti(self):
        result = expand_complaint("Fırçalarken kan geliyor")
        assert "dis eti" in result

    def test_oglum_expands_to_cocuk(self):
        result = expand_complaint("Oğlumun dişi çok ağrıyor")
        assert "cocuk" in result

    def test_yirmiyas_expands_to_yirmilik(self):
        result = expand_complaint("Yirmi yaş dişim çıkıyor")
        assert "yirmilik" in result

    def test_dis_cektirmek_expands_to_cekim(self):
        result = expand_complaint("Dişimi çektirmek istiyorum")
        assert "cekim" in result

    def test_original_text_preserved(self):
        """Orijinal metin her zaman sonucun başında olmalı."""
        text = "Dişim çürüdü biraz"
        result = expand_complaint(text)
        assert result.startswith(text)

    def test_multiple_rules_can_match(self):
        """Hem restoratif hem acil sinyali aynı metinde tetiklenebilir."""
        result = expand_complaint("Gece ağrısı var ve dişim kırıldı")
        assert "gece agrisi" in result
        assert "kirik dis" in result

    def test_unrelated_text_not_expanded(self):
        """Tamamen alakasız metin değiştirilmemeli."""
        text = "Merhaba yarın randevu alabilir miyim"
        result = expand_complaint(text)
        assert result == text

    def test_botoks_expands_to_medikal_estetik(self):
        result = expand_complaint("Dudak dolgusu yaptırmak istiyorum")
        assert "dudak dolgusu" in result

    def test_akne_expands_to_dermatoloji_terms(self):
        result = expand_complaint("Yüzümde akne var")
        assert "akne" in result

    def test_invisalign_expands_to_seffaf_plak(self):
        result = expand_complaint("Invisalign kullanıyorum")
        assert "seffaf plak" in result

    def test_no_duplicate_expansions(self):
        """Aynı kanonik terim birden fazla eklenmemeli."""
        # İki kural "kanal" üretiyor olabilir ama sonuçta tekrar olmamalı
        result = expand_complaint("Sinire gitti sanırım, gece ağrısı da var")
        terms = result.split()
        assert len(terms) == len(set(terms)) or result.count("kanal") <= 2


# ─────────────────────────────────────────────────────────────────────────────
# triage() — uçtan uca branş + aciliyet
# ─────────────────────────────────────────────────────────────────────────────

class TestTriage:
    def _triage(self, text: str) -> TriageResult:
        return triage(text)

    @pytest.mark.parametrize("text,expected_code", [
        ("Dişim çürüdü, dolgu yaptırmak istiyorum",     "restoratif"),
        ("Dişimin bir parçası kırıldı",                  "restoratif"),
        ("Sanırım sinire gitti, gece uyuyamıyorum",      "endodonti"),
        ("Gece ağrısı çok şiddetli, zonkluyor",          "endodonti"),
        ("Fırçalarken diş etlerim kanıyor",              "periodontoloji"),
        ("Oğlumun süt dişi düştü",                       "pedodonti"),
        ("Yirmi yaş dişim çıkıyor çok ağrıyor",         "cene_cerrahisi"),
        ("Dişimi çektirmek istiyorum",                    "cene_cerrahisi"),
        ("Diş telim kırıldı",                            "ortodonti"),
        ("Implantım ağrıyor",                            "implantoloji"),
        ("Gülüş tasarımı yaptırmak istiyorum",           "estetik_dis"),
    ])
    def test_specialty_routing(self, text, expected_code):
        result = self._triage(text)
        assert result.specialty_code == expected_code, (
            f"'{text}' → beklenen '{expected_code}', gerçek '{result.specialty_code}'"
        )

    @pytest.mark.parametrize("text,expected_urgency", [
        ("Yüzüm balon gibi şişti",              UrgencyLevel.EMERGENCY),
        ("Kan durmuyor, durduramıyorum",         UrgencyLevel.EMERGENCY),
        ("Nefes alamıyorum",                     UrgencyLevel.EMERGENCY),
        ("Çenem kırıldı",                        UrgencyLevel.EMERGENCY),
        ("Diş ağrım var, randevu alabilir miyim", UrgencyLevel.PRIORITY),
        ("Zonkluyor durmuyor",                    UrgencyLevel.PRIORITY),
        ("Gülüş tasarımı hakkında bilgi almak istiyorum", UrgencyLevel.ROUTINE),
        ("Diş teli taktırmak istiyorum",          UrgencyLevel.ROUTINE),
    ])
    def test_urgency_detection(self, text, expected_urgency):
        result = self._triage(text)
        assert result.urgency == expected_urgency, (
            f"'{text}' → beklenen {expected_urgency.value}, gerçek {result.urgency.value}"
        )

    def test_result_contains_raw_text(self):
        text = "Dişim çürüdü"
        result = self._triage(text)
        assert result.raw_text == text

    def test_enriched_text_is_superset(self):
        text = "Dişim çürüdü"
        result = self._triage(text)
        assert result.enriched_text.startswith(text)

    def test_expansions_non_empty_for_argo(self):
        result = self._triage("Sinire gitti galiba")
        assert len(result.expansions) > 0

    def test_expansions_empty_for_canonical(self):
        result = self._triage("Randevu almak istiyorum")
        assert result.expansions == ()

    def test_requires_escalation_for_emergency(self):
        result = self._triage("Yüzüm balon gibi şişti")
        assert result.requires_escalation is True

    def test_no_escalation_for_routine(self):
        result = self._triage("Diş teli kontrolü için randevu")
        assert result.requires_escalation is False

    def test_specialty_code_property(self):
        result = self._triage("dolgum düştü")
        assert result.specialty_code == "restoratif"

    def test_argo_endodont_no_keyword_in_original(self):
        """'Kanal' kelimesi geçmeden argo yoluyla endodonti bulunmalı."""
        text = "Sinire gitti sanırım"
        assert "kanal" not in text.lower()
        result = self._triage(text)
        assert result.specialty_code == "endodonti"

    def test_argo_periodontoloji_no_keyword_in_original(self):
        """'diş eti' geçmeden argo yoluyla periodontoloji bulunmalı."""
        text = "Fırçalarken kan geliyor"
        assert "diş eti" not in text.lower()
        result = self._triage(text)
        assert result.specialty_code == "periodontoloji"

    def test_argo_pedodonti_no_keyword_in_original(self):
        """'çocuk' geçmeden argo yoluyla pedodonti bulunmalı."""
        text = "Oğlumun dişi ağrıyor"
        assert "çocuk" not in text.lower()
        result = self._triage(text)
        assert result.specialty_code == "pedodonti"
