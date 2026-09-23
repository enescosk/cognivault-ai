"""Provider payload adapters only. No HTTP delivery or public webhook enabled.

Ingress must verify provider signature and match the sender to an open case
before passing the location to operations.Action. Phone destinations are supplied
by trusted server configuration when the adapter is connected to a real number.
"""
import re
from xml.etree.ElementTree import Element, SubElement, tostring

from pydantic import Field
from app.automotive.operations import Location, StrictModel


class WhatsAppLocation(StrictModel):
    type: str = 'location'
    location: Location
    message_id: str = Field(min_length=1, max_length=200)


def parse_meta_location(message: dict) -> dict:
    if message.get('type') != 'location' or not message.get('id'):
        raise ValueError('Konum mesajı ve sağlayıcı olay kimliği gerekli.')
    raw = message.get('location') or {}
    value = Location(latitude=raw.get('latitude'), longitude=raw.get('longitude'),
                     address=raw.get('address') or raw.get('name') or '', source='whatsapp')
    return dict(location=value.model_dump(), event_key=message['id'])


def location_payload(*, team_phone: str, location: Location) -> dict:
    if not re.fullmatch(r'\+[1-9]\d{7,14}', team_phone):
        raise ValueError('Ekip numarası E.164 biçiminde olmalı.')
    return dict(messaging_product='whatsapp', to=team_phone[1:], type='location',
                location=dict(latitude=location.latitude, longitude=location.longitude,
                              name='Yol yardım talebi', address=location.address))


def transfer_twiml(team_phone: str | None = None) -> str:
    root = Element('Response')
    SubElement(root, 'Say', language='tr-TR', voice='alice').text = (
        'Atlas Yol Yardım hattına hoş geldiniz. Size nasıl yardımcı olabiliriz? '
        'Yardım ekibimize aktarmayı deniyorum.' if team_phone else
        'Atlas Yol Yardım hattına hoş geldiniz. Ben dijital asistanınızım. '
        'Nasıl yardımcı olabilirim? Telefon ekibi bağlantısı henüz yapılandırılmamış. '
        'Yakın tehlike veya yaralanma varsa 112 acil çağrı merkezini arayın.')
    if team_phone:
        if not re.fullmatch(r'\+[1-9]\d{7,14}', team_phone):
            raise ValueError('Doğrulanmış ekip numarası gerekli.')
        dial = SubElement(root, 'Dial', answerOnBridge='true', timeout='20')
        SubElement(dial, 'Number').text = team_phone
        SubElement(root, 'Say', language='tr-TR', voice='alice').text = (
            'Ekip görüşmesi sona erdi veya bağlantı kurulamadı. Yardım ihtiyacınız sürüyorsa '
            'servis danışmanımızla yeniden iletişime geçin. Bu arama çekici sevk edildiği anlamına gelmez.')
    return tostring(root, encoding='unicode')
