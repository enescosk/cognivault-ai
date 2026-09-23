"""Rules consume service-owned facts; no model invents a maintenance interval.

This pilot has no delivery or booking adapter. All results are previews, never
proof of consent, completed dispatch, a reserved slot, or a persisted opt-out.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

Channel = Literal['sms', 'phone', 'whatsapp']


class VehicleRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    vehicle_id: str = Field(min_length=1, max_length=80)
    customer_label: str = Field(min_length=1, max_length=100)
    vehicle_label: str = Field(min_length=1, max_length=100)
    source_ref: str = Field(min_length=1, max_length=160)
    synced_on: date
    next_service_on: date | None = None
    next_service_km: int | None = Field(default=None, ge=1, le=3_000_000)
    odometer_km: int | None = Field(default=None, ge=0, le=3_000_000)
    odometer_on: date | None = None
    permitted_channels: list[Channel] = Field(default_factory=list)
    consent_ref: str | None = Field(default=None, min_length=1, max_length=160)
    consent_checked_on: date | None = None
    do_not_contact: bool = False
    ownership_verified: bool = False
    open_booking: bool = False
    last_contact_on: date | None = None

    @model_validator(mode='after')
    def mileage_pair(self):
        if (self.odometer_km is None) != (self.odometer_on is None):
            raise ValueError('Kilometre ve ölçüm tarihi birlikte verilmelidir.')
        return self


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    as_of: date
    channel: Channel = 'sms'
    records: list[VehicleRecord] = Field(min_length=1, max_length=500)

    @model_validator(mode='after')
    def unique_records(self):
        ids = [r.vehicle_id for r in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError('Aynı araç listede birden fazla kez bulunamaz.')
        return self


class Decision(BaseModel):
    vehicle_id: str
    customer_label: str
    vehicle_label: str
    status: Literal['ready', 'review', 'blocked', 'not_due']
    reason: str
    evidence: list[str]
    draft: str | None = None


def evaluate(record: VehicleRecord, as_of: date, channel: Channel) -> Decision:
    def result(status, reason, evidence=None, draft=None):
        return Decision(vehicle_id=record.vehicle_id, customer_label=record.customer_label,
                        vehicle_label=record.vehicle_label, status=status, reason=reason,
                        evidence=evidence or [], draft=draft)

    if record.do_not_contact:
        return result('blocked', 'İletişim reddi var; yeniden arama/mesaj planlanmaz.')
    if not record.ownership_verified:
        return result('blocked', 'Araç sahipliği veya iletişim eşleşmesi doğrulanmamış.')
    if channel not in record.permitted_channels or not record.consent_ref:
        return result('blocked', 'Bu kanal için belgeli iletişim izni yok.')
    if record.consent_checked_on != as_of:
        return result('blocked', 'Güncel kanal izni kontrolü gerekli (pilot: aynı gün).')
    if record.open_booking:
        return result('blocked', 'Aktif randevu var; yeni bakım kampanyasına alınmaz.')
    dates = [record.synced_on, record.odometer_on, record.last_contact_on]
    if any(value and value > as_of for value in dates):
        return result('review', 'Gelecek tarihli kayıt var; veri kaynağı kontrol edilmeli.')
    if record.last_contact_on and (as_of - record.last_contact_on).days < 30:
        return result('blocked', 'Son 30 gün içinde temas edilmiş (pilot sıklık sınırı).')
    if (as_of - record.synced_on).days > 7:
        return result('review', 'Servis kaydı güncel değil; önce kaynak sistemle eşitleyin.')
    evidence = [f'Kaynak: {record.source_ref}; eşitleme: {record.synced_on.isoformat()}']
    date_due = record.next_service_on is not None and record.next_service_on <= as_of + timedelta(days=30)
    mileage_fresh = record.odometer_on is not None and (as_of - record.odometer_on).days <= 30
    mileage_due = (record.next_service_km is not None and mileage_fresh
                   and record.odometer_km is not None and record.odometer_km >= record.next_service_km)
    if date_due:
        evidence.append(f'Servisin kayıtlı bakım tarihi: {record.next_service_on.isoformat()}')
    if mileage_due:
        evidence.append(f'Kayıtlı kilometre: {record.odometer_km}; bakım eşiği: {record.next_service_km}')
    if date_due or mileage_due:
        if date_due:
            basis = f'Servis kayıtlarımızda sonraki bakım tarihiniz {record.next_service_on:%d.%m.%Y} olarak görünüyor.'
        else:
            basis = f'Son paylaştığınız {record.odometer_km:,} km bilgisi, kayıtlı {record.next_service_km:,} km bakım eşiğine ulaşmış görünüyor.'
        draft = (f'Merhaba {record.customer_label}, Atlas Oto Servis dijital asistanıyım. '
                 f'{basis} Bakımınızı başka bir yerde yaptırdıysanız kaydımızı güncelleyebiliriz. '
                 'Dilerseniz uygun servis saatlerini kontrol edelim. '
                 'Bu hatırlatmaları almak istemiyorsanız İPTAL yazabilirsiniz.')
        if channel == 'phone':
            draft = ('Merhaba, Atlas Oto Servis dijital asistanıyım. Servis planlamanız hakkında '
                     'konuşmak için uygun musunuz? İstemiyorsanız arama tercihinizi kapatabiliriz. '
                     '[Kimlik ve araç ilişkisi doğrulandıktan sonra] '
                     f'{basis} Bakımınızı başka bir yerde yaptırdıysanız kaydımızı güncelleyebiliriz. '
                     'Dilerseniz uygun servis saatlerini kontrol edelim.')
        return result('ready', 'Kayıtlı bakım eşiği nedeniyle iletişim taslağı hazırlanabilir.', evidence, draft)
    if record.next_service_on is None and record.next_service_km is None:
        return result('review', 'Bakım planı bilinmiyor; bakım zamanı geldiği söylenemez.', evidence)
    if record.next_service_km is not None and not mileage_fresh:
        return result('review', 'Kilometre bilgisi eksik veya eski; önce kayıt güncellemesi gerekli.', evidence)
    return result('not_due', 'Kayıtlı tarih/kilometre eşiğine göre henüz aday değil.', evidence)


def preview(body: PreviewRequest) -> dict:
    decisions = [evaluate(row, body.as_of, body.channel) for row in body.records]
    return {'mode': 'preview', 'company': 'Atlas Oto Servis (kurgusal)',
            'as_of': body.as_of, 'channel': body.channel,
            'delivery_enabled': False, 'booking_enabled': False,
            'summary': {status: sum(d.status == status for d in decisions)
                        for status in ('ready', 'review', 'blocked', 'not_due')},
            'decisions': decisions}


def demo_data(today: date | None = None) -> PreviewRequest:
    today = today or datetime.now(ZoneInfo('Europe/Istanbul')).date()
    base = dict(source_ref='DEMO-DMS/2026', synced_on=today,
                next_service_on=today + timedelta(days=12), ownership_verified=True,
                permitted_channels=['sms', 'phone'], consent_ref='DEMO-IZIN-001', consent_checked_on=today)
    rows = [
        ('demo-01', 'Deniz', 'Araç A · demo', {}),
        ('demo-02', 'Ece', 'Araç B · demo', {'next_service_on': None, 'next_service_km': 60000,
                                          'odometer_km': 60500, 'odometer_on': today - timedelta(days=2)}),
        ('demo-03', 'Can', 'Araç C · demo', {'do_not_contact': True}),
        ('demo-04', 'Aslı', 'Araç D · demo', {'open_booking': True}),
        ('demo-05', 'Bora', 'Araç E · demo', {'next_service_on': None, 'next_service_km': 90000,
                                           'odometer_km': 75000, 'odometer_on': today - timedelta(days=120)}),
        ('demo-06', 'Selin', 'Araç F · demo', {'next_service_on': today + timedelta(days=100)}),
        ('demo-07', 'Mert', 'Araç G · demo', {'permitted_channels': []}),
        ('demo-08', 'Derya', 'Araç H · demo', {'last_contact_on': today - timedelta(days=5)}),
    ]
    return PreviewRequest(as_of=today, records=[VehicleRecord(
        **(base | changes | dict(vehicle_id=key, customer_label=name, vehicle_label=vehicle)))
        for key, name, vehicle, changes in rows])


class RehearsalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    vehicle_id: str = Field(min_length=1, max_length=80)
    outcome: Literal['interested', 'already_serviced', 'opt_out', 'wrong_person', 'price', 'urgent', 'human']


def rehearse(body: RehearsalRequest) -> dict:
    data = demo_data()
    rows = {r.vehicle_id: r for r in data.records}
    if body.vehicle_id not in rows:
        raise KeyError(body.vehicle_id)
    outcomes = {
        'interested': ('availability_required', 'Uygun gün ve saat aralığınız nedir? Servis takviminde kapasite doğrulandıktan ve siz onayladıktan sonra randevu oluşturulabilir.',
                       ['DMS: şube, bakım türü, lift/teknisyen süresi sorgula', 'Uygun slotu kısa süre tut', 'Müşteriden açık onay al', 'Tekrarlı isteğe dayanıklı kayıt oluştur; DMS randevu kimliğini doğrula', 'Onayı uygun kanaldan bildir']),
        'already_serviced': ('record_update_required', 'Bilgi için teşekkürler. Bakımın tarihini ve o tarihteki kilometreyi paylaşır mısınız? Servis danışmanımız kaydı doğrulayarak planı güncelleyebilir.',
                             ['Yeni kampanya temasını durdur', 'Müşteri beyanını doğrulanmamış kayıt olarak kaydet', 'Danışman onayı sonrası sonraki bakım planını güncelle']),
        'opt_out': ('suppression_required', 'Talebiniz alındı. Canlı sistemde iletişim tercihiniz kapatılır ve bekleyen bu tür hatırlatmalar durdurulur. Bu prova herhangi bir kaydı değiştirmez.',
                    ['Ret kaydını kalıcı yaz', 'Bekleyen temasları iptal et', 'İzin kaynağına/İYS sürecine ilet', 'İşlem başarılı olmadan tamamlandı deme']),
        'wrong_person': ('identity_review_required', 'Kusura bakmayın. Araç bilgisi paylaşmadan görüşmeyi sonlandırıyorum. İletişim eşleşmesinin kontrol edilmesi gerekiyor.',
                         ['Bu adres için kampanyayı durdur', 'Araç ve kişi eşleşmesini insan incelemesine gönder']),
        'price': ('quote_required', 'Ücret bakım kapsamına ve kullanılacak parçalara göre değişir. Servis danışmanından yazılı teklif isteyebiliriz; doğrulanmış teklif olmadan fiyat veremem.',
                  ['Araç/işlem için güncel fiyat teklifini DMS üzerinden al', 'Geçerlilik, vergi ve kapsamı belirt', 'Ek iş için ayrıca müşteri onayı al']),
        'urgent': ('human_handoff', 'Bu belirti için bakım kampanyasına devam etmeyelim. Güvenliğinizi önceliklendirin; servis danışmanı veya yol yardımına bağlanmanız gerekiyor. Buradan arıza teşhisi koyamam.',
                   ['Kampanyayı durdur', 'Acil insan/yol yardımı aktarımı iste', 'Aktarım başarısızsa doğrulanmış alternatif iletişimi göster']),
        'human': ('human_handoff', 'Servis danışmanıyla görüşme talebinizi iletmek için görüşme özetini hazırlıyorum.',
                  ['İzinli görüşme özetini hazırla', 'Danışmanın uygunluğunu kontrol et', 'Canlı aktar veya geri arama talebi oluştur']),
    }
    stage, reply, steps = outcomes[body.outcome]
    decision = evaluate(rows[body.vehicle_id], data.as_of, 'sms')
    if body.outcome == 'interested' and decision.status != 'ready':
        stage, reply, steps = 'blocked', decision.reason, ['Önce adaylık engelini incele; kampanya başlatma']
    return {'mode': 'rehearsal', 'persisted': False, 'booking_confirmed': False,
            'stage': stage, 'reply': reply, 'required_steps': steps}
