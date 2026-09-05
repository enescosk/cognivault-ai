"""Bir iletişim numarasını (telefon/WhatsApp) bir kliniğe bağlar.

Multi-tenant webhook yönlendirmesi (`resolve_webhook_clinic`) gelen çağrının/
mesajın hangi kliniğe ait olduğunu `ClinicChannelBinding` üzerinden çözer. Bu
script o kaydı elle oluşturur/günceller — Netgsm↔Twilio SIP trunk kurulumunun
(bkz. `docs/ops/netgsm-twilio-sip-trunk-kurulumu.md`) **Adım 4**'ü: aranan +90
numarayı gerçek kliniğe bağlar. `CLINICAL_CHANNEL_BINDING_STRICT=true` iken bu
kayıt yoksa çağrı "Bu numara şu anda hizmet dışıdır" ile reddedilir.

Adres, webhook'un okuduğu `To` ile **aynı** `normalize_phone` fonksiyonundan
geçirilir (tek doğru kaynak) — böylece kayıt ile arama birebir eşleşir. Kayıt
(kanal, adres) üzerinde tekildir; script idempotenttir: aynı numara tekrar
bağlanırsa var olan kayıt hedef kliniğe yeniden yönlendirilip aktifleştirilir,
çift kayıt oluşmaz.

Kullanım (backend/ dizininden):
    python -m app.ops.bind_channel --clinic demo-klinik --phone "+90 312 000 00 00"
    python -m app.ops.bind_channel --clinic demo-klinik --phone "+90..." --channel whatsapp
    python -m app.ops.bind_channel --clinic demo-klinik --phone "+90..." --deactivate
    python -m app.ops.bind_channel --list
"""
from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Clinic, ClinicChannel, ClinicChannelBinding
from app.services.clinical_service import normalize_phone


def _clinic_by_slug(db: Session, slug: str) -> Clinic | None:
    return db.scalars(select(Clinic).where(Clinic.slug == slug)).first()


def _available_slugs(db: Session) -> list[str]:
    return list(db.scalars(select(Clinic.slug).order_by(Clinic.slug)).all())


def list_bindings(db: Session) -> int:
    rows = db.scalars(
        select(ClinicChannelBinding).order_by(
            ClinicChannelBinding.channel, ClinicChannelBinding.address
        )
    ).all()
    if not rows:
        print("Kayıtlı kanal bağlantısı yok.")
        return 0
    print(f"{'KANAL':<10} {'ADRES':<22} {'AKTİF':<6} KLİNİK")
    print("-" * 60)
    for b in rows:
        clinic = db.get(Clinic, b.clinic_id)
        clinic_label = f"{clinic.slug} ({clinic.name})" if clinic else f"#{b.clinic_id} (bulunamadı)"
        active = "✓" if b.is_active else "✗"
        print(f"{b.channel.value:<10} {b.address:<22} {active:<6} {clinic_label}")
    return 0


def bind_channel(
    db: Session, *, clinic_slug: str, phone: str, channel: ClinicChannel, deactivate: bool
) -> int:
    address = normalize_phone(phone)
    if not address:
        print("HATA: --phone boş görünüyor (normalize sonrası).")
        return 2

    clinic = _clinic_by_slug(db, clinic_slug)
    if clinic is None:
        print(f"HATA: '{clinic_slug}' slug'lı klinik yok.")
        slugs = _available_slugs(db)
        if slugs:
            print("Mevcut klinikler: " + ", ".join(slugs))
        return 2

    existing = db.scalars(
        select(ClinicChannelBinding).where(
            ClinicChannelBinding.channel == channel,
            ClinicChannelBinding.address == address,
        )
    ).first()

    if deactivate:
        if existing is None:
            print(f"Not: {channel.value}/{address} için zaten kayıt yok, yapılacak bir şey yok.")
            return 0
        existing.is_active = False
        db.commit()
        print(f"✓ Devre dışı: {channel.value}/{address} (klinik: {clinic.slug})")
        return 0

    if existing is None:
        db.add(
            ClinicChannelBinding(
                clinic_id=clinic.id, channel=channel, address=address, is_active=True
            )
        )
        db.commit()
        print(f"✓ Oluşturuldu: {channel.value}/{address} → {clinic.slug} ({clinic.name})")
        return 0

    # Idempotent güncelleme: hedef kliniğe yeniden yönlendir + aktifleştir.
    repoint = existing.clinic_id != clinic.id
    reactivate = not existing.is_active
    existing.clinic_id = clinic.id
    existing.is_active = True
    db.commit()
    changes = []
    if repoint:
        changes.append("yeniden yönlendirildi")
    if reactivate:
        changes.append("aktifleştirildi")
    suffix = f" ({', '.join(changes)})" if changes else " (değişiklik yok)"
    print(f"✓ Güncellendi: {channel.value}/{address} → {clinic.slug} ({clinic.name}){suffix}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="İletişim numarasını (telefon/WhatsApp) bir kliniğe bağla — multi-tenant webhook yönlendirmesi."
    )
    parser.add_argument("--clinic", help="Klinik slug'ı (ör. demo-klinik)")
    parser.add_argument("--phone", help="Aranan numara / WABA adresi (E.164 önerilir, ör. +90312...)")
    parser.add_argument(
        "--channel",
        default="phone",
        choices=[c.value for c in ClinicChannel],
        help="Kanal (varsayılan: phone)",
    )
    parser.add_argument("--deactivate", action="store_true", help="Kaydı devre dışı bırak (is_active=False)")
    parser.add_argument("--list", action="store_true", help="Tüm kanal bağlantılarını listele")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        if args.list:
            return list_bindings(db)
        if not args.clinic or not args.phone:
            parser.error("--clinic ve --phone gerekli (veya --list kullan).")
        return bind_channel(
            db,
            clinic_slug=args.clinic,
            phone=args.phone,
            channel=ClinicChannel(args.channel),
            deactivate=args.deactivate,
        )
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
