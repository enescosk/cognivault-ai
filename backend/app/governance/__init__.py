"""İP-2 — Deterministik Yönetişim Zarfı sertleştirme paketi.

Mevcut zarf (`services/clinical_compliance_service.build_governance_context`)
üstüne adversarial kapsam + ihlal-edilemezlik kanıtı ekler. Saf Python,
veritabanı/ağ yok — kapı mantığı `--noconftest` ile test edilebilir.
"""
