"""Persistent local dispatch rehearsal. Provider delivery is deliberately disabled."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AutomotiveCase, User

CATALOG = [
    dict(id='tow', title='Çekici çağır', group='Yol yardımı', icon='↗', description='Arızalı aracı uygun çekiciyle servise taşıma', prompt='Aracım çalışmıyor, çekici gerekiyor.', mobile=True, capability='flatbed'),
    dict(id='battery', title='Akü / çalışmama', group='Yol yardımı', icon='ϟ', description='Yerinde ekip değerlendirmesi; gerekirse çekici', prompt='Akü bitmiş olabilir, araba çalışmıyor.', mobile=True, capability='battery'),
    dict(id='tire', title='Lastik yardımı', group='Yol yardımı', icon='◉', description='Konum, yedek lastik ve ekip uygunluğu', prompt='Lastiğim patladı, yolda kaldım.', mobile=True, capability='tire'),
    dict(id='fuel', title='Yakıt bitti', group='Yol yardımı', icon='◈', description='Yakıt türü ve uygun destek ekibi kontrolü', prompt='Benzinim bitti, yolda kaldım.', mobile=True, capability='fuel'),
    dict(id='locked', title='Anahtar içeride', group='Yol yardımı', icon='⌁', description='Sahiplik kontrolüyle yetkili ekip yönlendirme', prompt='Anahtar içeride kaldı, kapı kilitli.', mobile=True, capability='locksmith'),
    dict(id='ev', title='Elektrikli araç', group='Yol yardımı', icon='⚡', description='Uygun taşıma ekipmanı ve uzman danışman', prompt='Elektrikli aracımın şarjı bitti.', mobile=True, capability='ev_flatbed'),
    dict(id='accident', title='Kaza / hasar', group='Yol yardımı', icon='!', description='Önce güvenlik ve acil durum; sonra hasar/çekici', prompt='Kaza yaptım, aracım hasarlı.', mobile=True, capability='flatbed'),
    dict(id='maintenance', title='Bakım randevusu', group='Servis', icon='◷', description='Üretici planı ve gerçek servis kapasitesi', prompt='Periyodik bakım için randevu istiyorum.', mobile=False),
    dict(id='repair', title='Arıza / kontrol', group='Servis', icon='⌘', description='Belirti kaydı, danışman ve kontrol talebi', prompt='Aracım ses yapıyor, kontrol ettirmek istiyorum.', mobile=False),
    dict(id='inspection', title='Muayene hazırlığı', group='Servis', icon='✓', description='Servis ön kontrolü; resmî muayene randevusu değildir', prompt='Muayene öncesi kontrol yaptırmak istiyorum.', mobile=False),
    dict(id='status', title='Aracım ne durumda?', group='Servis', icon='◎', description='İş emrinden doğrulanmış onarım ve teslim bilgisi', prompt='Servisteki aracım hazır mı?', mobile=False),
    dict(id='quote', title='Teklif / ek iş onayı', group='Servis', icon='₺', description='Kapsam, tutar ve açık müşteri onayı', prompt='Onarım fiyatını öğrenmek istiyorum.', mobile=False),
    dict(id='pickup', title='Vale / araç alımı', group='Servis', icon='⇄', description='Teslim alma adresi ve danışman planlaması', prompt='Aracımı adresimden alabilir misiniz?', mobile=False),
    dict(id='fleet', title='Filo / çoklu araç', group='Servis', icon='▦', description='Araç listesi, sözleşme ve toplu kapasite', prompt='Şirket araçlarımız için bakım planlayalım.', mobile=False),
    dict(id='complaint', title='Şikâyet / tekrar kontrol', group='Servis', icon='☏', description='Önceki iş emriyle insan danışmana öncelikli aktarım', prompt='Bakım sonrası aynı sorun devam ediyor.', mobile=False),
]
SERVICES = {item['id']: item for item in CATALOG}
TEAMS = [
    dict(id='atlas-01', name='Atlas Çekici 1', kind='Platform çekici', capabilities=['flatbed', 'ev_flatbed'], lat=41.015, lon=29.04, radius_km=45, available=True),
    dict(id='atlas-02', name='Atlas Mobil Destek', kind='Akü · lastik · yakıt', capabilities=['battery', 'tire', 'fuel'], lat=41.025, lon=29.09, radius_km=30, available=True),
    dict(id='atlas-03', name='Atlas Çekici 2', kind='Platform çekici', capabilities=['flatbed'], lat=40.99, lon=29.12, radius_km=45, available=False),
]
STATUS_LABELS = dict(intake='Bilgiler alınıyor', needs_location='Konum bekleniyor', ready='Ekip seçilebilir', offered='Ekibe teklif edildi', accepted='Ekip kabul etti', en_route='Ekip yolda', arrived='Ekip ulaştı', transporting='Araç taşınıyor', completed='Tamamlandı', cancelled='İptal', human='Danışman bekleniyor', emergency='Acil yardım önceliği', service_requested='Servis talebi açık')
CLOSED = {'completed', 'cancelled'}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class CreateCase(StrictModel):
    request_key: str = Field(min_length=8, max_length=80)
    service: str
    customer: str = Field(default='Örnek müşteri', min_length=1, max_length=80)
    channel: Literal['phone', 'whatsapp', 'web'] = 'phone'

    @model_validator(mode='after')
    def service_known(self):
        if self.service not in SERVICES:
            raise ValueError('Bilinmeyen servis türü')
        return self


class Location(StrictModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    address: str = Field(default='', max_length=300)
    source: Literal['whatsapp', 'manual'] = 'manual'


class Action(StrictModel):
    event_key: str = Field(min_length=8, max_length=80)
    version: int = Field(ge=1)
    kind: Literal['details', 'location', 'share', 'offer', 'accept', 'decline', 'en_route', 'arrived', 'transport', 'complete', 'cancel', 'cancel_confirmed', 'human', 'emergency', 'message']
    text: str = Field(default='', max_length=1200)
    vehicle: str = Field(default='', max_length=120)
    destination: str = Field(default='', max_length=200)
    safe: bool | None = None
    location: Location | None = None
    permission: bool | None = None
    team_id: str | None = Field(default=None, max_length=80)
    eta_minutes: int | None = Field(default=None, ge=1, le=300)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def scoped(user):
    # Deliberately owner-only even within an organization for this local pilot.
    # No legacy default-organization fallback and no cross-user demo sharing.
    return [AutomotiveCase.owner_id == user.id,
            AutomotiveCase.organization_id == user.organization_id if user.organization_id is not None
            else AutomotiveCase.organization_id.is_(None)]


def fetch(db, user, case_id):
    row = db.scalar(select(AutomotiveCase).where(AutomotiveCase.id == case_id, *scoped(user)))
    if not row:
        raise HTTPException(404, 'Talep bulunamadı.')
    return row


def public(row):
    data = deepcopy(row.data)
    data.pop('events', None)
    data.pop('create_hash', None)
    # Gelen kanal işlerinde müşteri numarası panelde maskelenir; ham numara
    # yalnız gönderim için sunucuda kalır.
    if data.get('contact'):
        phone = data['contact']
        data['contact'] = phone[:4] + '•' * max(0, len(phone) - 8) + phone[-4:]
    from app.core.config import get_settings

    live = get_settings().automotive_whatsapp_enabled
    return dict(id=row.id, version=row.version, mode='live' if live else 'local_demo', delivery_enabled=live,
                status_label=STATUS_LABELS[data['status']], **data)


def add_reply(data, text):
    data['messages'].append(dict(role='assistant', text=text, at=stamp()))


def new_case_data(*, service_id: str, customer: str, channel: str, fingerprint: str) -> dict:
    """Yeni iş kaydının başlangıç verisi — operatör paneli ve gelen kanal ortak."""
    from app.core.config import get_settings

    settings = get_settings()
    service = SERVICES[service_id]
    greeting = (f'{settings.automotive_brand} hattına hoş geldiniz. Ben dijital asistanınızım. Nasıl yardımcı olabilirim? '
                'Önce siz ve araçtaki kişiler güvende misiniz? Yaralanma, yangın veya yakın tehlike var mı?') if service['mobile'] else (
                f'{settings.automotive_service_name}’e hoş geldiniz. Ben dijital asistanınızım. Size nasıl yardımcı olabilirim?')
    data = dict(service=service_id, service_title=service['title'], customer=customer, channel=channel,
                status='intake', vehicle='', destination='', safe=None, location=None, share_permission=False,
                assigned_team=None, eta_minutes=None, handoff=None, dispatch_started=False, messages=[], audit=[], events={}, create_hash=fingerprint)
    add_reply(data, greeting)
    data['audit'].append(dict(action='created', at=stamp(), detail='Yerel prova talebi açıldı.'))
    return data


def create_case(db: Session, user: User, body: CreateCase):
    fingerprint = digest(body.model_dump())
    existing = db.scalar(select(AutomotiveCase).where(*scoped(user), AutomotiveCase.request_key == body.request_key))
    if existing:
        if existing.data['create_hash'] != fingerprint:
            raise HTTPException(409, 'İstek anahtarı farklı bir talepte kullanılmış.')
        return public(existing)
    data = new_case_data(service_id=body.service, customer=body.customer, channel=body.channel, fingerprint=fingerprint)
    row = AutomotiveCase(id=str(uuid4()), owner_id=user.id, organization_id=user.organization_id,
                         request_key=body.request_key, version=1, data=data)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AutomotiveCase).where(*scoped(user), AutomotiveCase.request_key == body.request_key))
        if existing and existing.data['create_hash'] == fingerprint:
            return public(existing)
        raise HTTPException(409, 'Talep anahtarı çakıştı.') from None
    db.refresh(row)
    return public(row)


def candidates(data):
    if not data['location']:
        return []
    capability = SERVICES[data['service']].get('capability')
    answer = []
    for team in TEAMS:
        loc = data['location']
        lat1, lat2 = math.radians(loc['latitude']), math.radians(team['lat'])
        a = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(math.radians(team['lon']-loc['longitude'])/2)**2
        distance = 6371 * 2 * math.asin(math.sqrt(min(1, a)))
        if team['available'] and capability in team['capabilities'] and distance <= team['radius_km']:
            answer.append(dict(id=team['id'], name=team['name'], kind=team['kind'], distance_km=round(distance, 1)))
    return sorted(answer, key=lambda t: t['distance_km'])


def ready(data):
    return data['safe'] is True and bool(data['vehicle']) and bool(data['destination']) and data['location'] is not None


def normalize(text):
    return text.translate(str.maketrans('İIŞĞÜÖÇ', 'iışğüöç')).lower()


def apply(data, action):
    status = data['status']
    mobile = SERVICES[data['service']]['mobile']
    if status in CLOSED:
        raise HTTPException(409, 'Kapanmış talep değiştirilemez; yeni talep açın.')
    if len(data['audit']) >= 150:
        raise HTTPException(409, 'Prova işlem sınırına ulaşıldı.')
    kind = action.kind
    if kind == 'message':
        text = action.text.strip()
        if not text:
            raise HTTPException(422, 'Mesaj boş olamaz.')
        data['messages'].append(dict(role='customer', text=text, at=stamp()))
        text = normalize(text)
        # Suspected emergencies always go to a human; absence of these words is
        # never treated as confirmation that a caller is safe.
        if any(word in text for word in ['yaralı', 'yaraland', 'yangın', 'yanıyor', 'sıkıştı', 'nefes alam', 'kanama']):
            kind = 'emergency'
        elif any(word in text for word in ['iptal', 'vazgeç']):
            kind = 'cancel'
        elif any(word in text for word in ['temsilci', 'insan', 'danışman', 'bağla']):
            kind = 'human'
        else:
            messages = {
                'status': 'Araç durumu için iş emri numaranızı alabilir miyim? Kaynak servis yazılımı bağlı olmadığı için hazır veya teslim saati bilgisi doğrulayamıyorum.',
                'quote': 'Araç ve işlem kapsamını kaydedelim. Vergi, parça ve işçilik kapsamı doğrulanmış teklif olmadan fiyat ya da ek iş onayı oluşturamam.',
                'complaint': 'Yaşadığınız sorunu ve önceki iş emrinizi kaydedip servis danışmanına aktaralım. Güvenlik riski varsa aracı kullanmaya devam etmenizi öneremem.',
                'fleet': 'Araç sayısı, bakım türleri ve tercih ettiğiniz günleri alalım. Filo sözleşmesi ve servis kapasitesi danışman tarafından doğrulanmalı.',
                'inspection': 'Muayene öncesi servis kontrolü için araç ve gün tercihinizi alalım. Bu talep resmî muayene randevusu oluşturmaz.',
                'pickup': 'Teslim alma adresi ve zaman tercihinizi alalım. Vale uygunluğu ve teslim tutanağı danışman tarafından doğrulanmalı.',
            }
            if 'fiyat' in text or 'ücret' in text:
                reply = 'Konum, araç ve hizmet kapsamına göre ekipten teklif alınmalı. Onayınız olmadan ücretli ek işlem başlatılmamalı; bu provada fiyat hesaplanmaz.'
            elif 'nerede' in text or 'kaç dakika' in text:
                reply = f"Talebinizin durumu: {STATUS_LABELS[status]}. " + (f"Ekibin bildirdiği tahmin {data['eta_minutes']} dakika; trafikle değişebilir." if data['eta_minutes'] else 'Doğrulanmış varış tahmini henüz yok.')
            elif mobile:
                reply = 'Önce güvenlik durumunuzu, araç türünü ve götürülecek yeri netleştirelim. WhatsApp üzerinden mevcut konum pininizi paylaşabilirsiniz; adres ve yol yönünü de teyit edeceğiz.'
            else:
                reply = messages.get(data['service'], 'Araç, talebiniz ve uygun gün/saat aralığını alalım. Gerçek servis takvimi doğrulanmadan randevu onayı veremem.')
            add_reply(data, reply)
            return
    if kind == 'emergency':
        data['status'] = 'emergency'
        add_reply(data, 'Yaralanma, yangın veya yakın tehlike varsa önce 112’yi arayın. Bu hat acil yardımın yerine geçmez. Normal sevk akışını durdurup insan değerlendirmesi istiyorum; bu prova acil servise çağrı yapmaz.')
    elif kind == 'human':
        data['status'] = 'human'
        add_reply(data, 'Görüşme özetiniz danışman kuyruğuna alındı. Canlı telefon bağlantısı yapılandırılınca görevli ekibe aktarılabilir; şu anda bağlantı kurulduğu anlamına gelmez.')
    elif kind == 'cancel':
        if data.get('dispatch_started'):
            data['status'] = 'human'
            add_reply(data, 'Ekip görevi kabul ettiği için iptal talebinizi danışmanla ve ekiple teyit etmemiz gerekiyor. Görev otomatik iptal edilmedi.')
        else:
            data['status'] = 'cancelled'
            data['assigned_team'] = None
            data['handoff'] = None
            data['eta_minutes'] = None
            add_reply(data, 'Yerel prova talebi iptal edildi. Gerçek bir ekibe bildirim gönderilmedi.')
    elif kind == 'cancel_confirmed':
        if status not in {'human', 'emergency'} or not data['assigned_team']:
            raise HTTPException(409, 'Önce danışman/ekip iptal değerlendirmesi gerekli.')
        data['status'] = 'cancelled'
        add_reply(data, 'Prova: ekip ve danışman iptali teyit etti; görev kapandı. Gerçek iptal bildirimi gönderilmedi.')
    elif kind in {'details', 'location', 'share'}:
        if status not in {'intake', 'needs_location', 'ready'}:
            raise HTTPException(409, 'Sevk sonrası konum/araç değişikliği danışman tarafından uzlaştırılmalı.')
        if kind == 'details':
            if not action.vehicle:
                raise HTTPException(422, 'Araç bilgisi gerekli.')
            data['vehicle'], data['destination'], data['safe'] = action.vehicle, action.destination, action.safe
            if action.safe is False:
                data['status'] = 'emergency'
                add_reply(data, 'Güvenli olmadığınızı belirttiniz. Yakın tehlike veya yaralanmada 112’yi arayın; talep insan değerlendirmesine ayrıldı.')
                return
            if not mobile:
                data['status'] = 'service_requested'
                add_reply(data, 'Servis talebiniz yerel panoya kaydedildi. Danışman kaynak sistemden kapasite, iş emri veya teklif bilgisini doğruladıktan sonra size kesin bilgi verebilir.')
                return
        elif kind == 'location':
            if not action.location:
                raise HTTPException(422, 'Geçerli koordinat gerekli.')
            data['location'] = action.location.model_dump() | {'received_at': stamp()}
            # New location invalidates prior sharing approval.
            data['share_permission'] = False
            add_reply(data, 'Konum pini alındı. Adres, yol yönü ve güvenli erişim noktasını teyit edelim. Seçilecek yardım ekibiyle paylaşılmasına izin veriyor musunuz?')
        elif kind == 'share':
            if not data['location'] or action.permission is None:
                raise HTTPException(422, 'Önce konum ve açık paylaşım tercihi gerekli.')
            data['share_permission'] = action.permission
            add_reply(data, 'Bu konum için ekip paylaşım tercihiniz kaydedildi.' if action.permission else 'Konum ekiple paylaşılmayacak; danışmanla alternatif yardım planlanabilir.')
        data['status'] = 'ready' if ready(data) else 'needs_location'
        if kind == 'details':
            add_reply(data, 'Araç bilgisi alındı. WhatsApp konumu veya doğrulanmış koordinat bekliyorum; ardından uygun ekibi kontrol edeceğiz.')
    elif kind == 'offer':
        if status != 'ready' or not ready(data) or not data['share_permission']:
            raise HTTPException(409, 'Sevk için güvenlik, araç, hedef, konum ve paylaşım izni gerekli.')
        age = datetime.now(timezone.utc) - datetime.fromisoformat(data['location']['received_at'])
        if age.total_seconds() > 1800:
            raise HTTPException(409, 'Konum 30 dakikadan eski; yeni pin ve paylaşım onayı alın.')
        team = next((t for t in candidates(data) if t['id'] == action.team_id), None)
        if not team:
            raise HTTPException(409, 'Ekip uygun değil veya kapsama alanı dışında.')
        loc = data['location']
        data['assigned_team'] = team
        data['handoff'] = dict(team_id=team['id'], customer=data['customer'], vehicle=data['vehicle'],
                               service=data['service_title'], destination=data['destination'], location=loc,
                               map_url=f"https://www.google.com/maps?q={loc['latitude']},{loc['longitude']}",
                               delivery_status='demo_only', note='Yol yönü, erişim, araç ekipmanı ve fiyat müşteriyle teyit edilmeli.')
        data['status'] = 'offered'
        add_reply(data, f"{team['name']} için konumlu iş kartı hazırlandı. Prova teklifinin ekip kabulü bekleniyor; henüz çekici yola çıkmadı.")
    elif kind == 'decline':
        if status != 'offered':
            raise HTTPException(409, 'Yalnız bekleyen ekip teklifi reddedilebilir.')
        data['status'], data['assigned_team'], data['handoff'], data['eta_minutes'] = 'ready', None, None, None
        add_reply(data, 'Ekip teklifi reddetti. Başka uygun ekip seçilebilir; uygun ekip yoksa danışmana aktarın.')
    elif kind == 'accept':
        if status != 'offered' or not data['assigned_team'] or action.eta_minutes is None:
            raise HTTPException(409, 'Bekleyen teklif ve ekibin bildirdiği varış tahmini gerekli.')
        data['status'], data['eta_minutes'] = 'accepted', action.eta_minutes
        data['dispatch_started'] = True
        add_reply(data, f"Prova: {data['assigned_team']['name']} talebi kabul etti. Ekibin bildirdiği tahmini varış {action.eta_minutes} dakika; henüz yola çıktı bildirimi yok.")
    else:
        transitions = {'en_route': ('accepted', 'en_route'), 'arrived': ('en_route', 'arrived'),
                       'transport': ('arrived', 'transporting')}
        if kind == 'complete':
            required = 'transporting' if SERVICES[data['service']].get('capability') in {'flatbed', 'ev_flatbed'} else 'arrived'
            transitions['complete'] = (required, 'completed')
        if kind not in transitions or status != transitions[kind][0]:
            raise HTTPException(409, 'Bu adım mevcut talep durumunda uygulanamaz.')
        data['status'] = transitions[kind][1]
        replies = {'en_route': 'Prova: ekibimiz yola çıktı; paylaştığınız konuma yönlendiriliyor. Varış tahmini trafik ve erişime göre değişebilir.',
                   'arrived': 'Prova: ekip konuma ulaştı. Araç ve hizmet kapsamını yüz yüze teyit edin.',
                   'transport': 'Prova: araç teslim alma kaydıyla taşıma başladı. Hedef servis bilgisi teyit edilmeli.',
                   'complete': 'Prova görevi tamamlandı. Teslim tutanağı, işlem sonucu ve varsa müşteri onaylı ücret gerçek sistemde kayıt altına alınmalı.'}
        add_reply(data, replies[kind])


def act(db, user, case_id, body):
    row = fetch(db, user, case_id)
    data = deepcopy(row.data)
    fingerprint = digest(body.model_dump(mode='json', exclude={'version'}))
    previous = data['events'].get(body.event_key)
    if previous:
        if previous != fingerprint:
            raise HTTPException(409, 'Olay anahtarı farklı işlemde kullanılmış.')
        return public(row)
    if row.version != body.version:
        raise HTTPException(409, 'Talep başka bir işlemle güncellendi. Listeyi yenileyin.')
    apply(data, body)
    data['events'][body.event_key] = fingerprint
    data['audit'].append(dict(action=body.kind, at=stamp(), detail=STATUS_LABELS[data['status']]))
    persist(db, user, row, data, expected_version=body.version)
    return public(row)


def persist(db: Session, user: User, row: AutomotiveCase, data: dict, *, expected_version: int,
            commit: bool = True) -> None:
    """Sürüm kontrollü yazım. `commit=False` ile çağıran aynı işleme başka
    satırlar (giden mesajlar, outbox) ekleyip tek seferde commit edebilir."""
    team_slot = data['assigned_team']['id'] if data['assigned_team'] and data['status'] not in CLOSED else None
    try:
        result = db.execute(update(AutomotiveCase).where(AutomotiveCase.id == row.id, *scoped(user),
                           AutomotiveCase.version == expected_version).values(data=data, version=expected_version + 1, team_slot=team_slot))
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Ekip başka açık görevde. Başka ekip seçin veya danışmana aktarın.') from None
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, 'Eşzamanlı işlem çakışması; listeyi yenileyin.')
    if commit:
        db.commit()
        db.refresh(row)
