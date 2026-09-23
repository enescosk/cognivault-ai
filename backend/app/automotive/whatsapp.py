"""Meta WhatsApp Cloud API — gelen webhook okuma, giden mesaj kurma, gönderim.

Bu modül iş kuralı içermez: neyin kime ne zaman gideceğine `roadside` karar
verir. Burada yalnız sağlayıcının biçimi durur.

Sağlayıcı sınırları (sessizce kesilmez, `ValueError` fırlatılır — kesmek
canlıda anlamsız buton başlıkları üretir, hata ise testte yakalanır):
- Yanıt butonu: en fazla 3, başlık en fazla 20 karakter, kimlik en fazla 256.
- Gövde metni en fazla 1024 karakter.

24 saat kuralı: işletme, son 24 saatte kendisine yazmamış birine serbest
(session) mesaj GÖNDEREMEZ; yalnız Meta'nın onayladığı şablon gidebilir.
Hangisinin kullanılacağına `roadside` karar verir; bu modül ikisini de kurar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

GRAPH_URL = 'https://graph.facebook.com/v21.0'
BUTTON_TITLE_MAX = 20
BUTTON_ID_MAX = 256
MAX_BUTTONS = 3
BODY_MAX = 1024
SESSION_WINDOW_SECONDS = 24 * 60 * 60
E164 = re.compile(r'\+[1-9]\d{7,14}')


# ─── Gelen ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Inbound:
    sender: str               # E.164 (+90...)
    message_id: str           # sağlayıcı kimliği — tekrar koruması anahtarı
    kind: str                 # text | location | reply | unsupported
    text: str = ''
    latitude: float | None = None
    longitude: float | None = None
    address: str = ''
    reply_id: str = ''        # bizim koyduğumuz buton kimliği
    name: str = ''


@dataclass(frozen=True)
class StatusUpdate:
    provider_message_id: str
    status: str               # sent | delivered | read | failed
    error: str = ''


def e164(wa_id: str) -> str:
    value = '+' + str(wa_id).lstrip('+')
    if not E164.fullmatch(value):
        raise ValueError('Geçersiz WhatsApp numarası')
    return value


def _parse_message(message: dict, names: dict[str, str]) -> Inbound | None:
    sender_raw, message_id = message.get('from'), message.get('id')
    if not sender_raw or not message_id:
        return None
    sender = e164(sender_raw)
    base = dict(sender=sender, message_id=message_id, name=names.get(sender_raw, ''))
    kind = message.get('type')
    if kind == 'text':
        return Inbound(kind='text', text=(message.get('text') or {}).get('body', '')[:1200], **base)
    if kind == 'location':
        loc = message.get('location') or {}
        try:
            lat, lon = float(loc['latitude']), float(loc['longitude'])
        except (KeyError, TypeError, ValueError):
            return Inbound(kind='unsupported', **base)
        address = ' — '.join(p for p in (loc.get('name'), loc.get('address')) if p)[:300]
        return Inbound(kind='location', latitude=lat, longitude=lon, address=address, **base)
    if kind == 'interactive':
        interactive = message.get('interactive') or {}
        reply = interactive.get('button_reply') or interactive.get('list_reply') or {}
        return Inbound(kind='reply', reply_id=str(reply.get('id', ''))[:BUTTON_ID_MAX],
                       text=str(reply.get('title', ''))[:120], **base)
    if kind == 'button':  # şablon hızlı yanıtı
        button = message.get('button') or {}
        return Inbound(kind='reply', reply_id=str(button.get('payload', ''))[:BUTTON_ID_MAX],
                       text=str(button.get('text', ''))[:120], **base)
    return Inbound(kind='unsupported', **base)


def parse_webhook(payload: dict, *, phone_number_id: str) -> tuple[list[Inbound], list[StatusUpdate]]:
    """Webhook gövdesini gelen mesaj ve teslim durumu listelerine ayırır.

    Başka bir numaraya (phone_number_id) ait değişiklikler ATLANIR — aynı Meta
    hesabında birden fazla numara olabilir ve başka işletmenin mesajı bu işe
    düşmemeli.
    """
    inbound: list[Inbound] = []
    statuses: list[StatusUpdate] = []
    for entry in payload.get('entry') or []:
        for change in entry.get('changes') or []:
            value = change.get('value') or {}
            if (value.get('metadata') or {}).get('phone_number_id') != phone_number_id:
                continue
            names = {c.get('wa_id'): (c.get('profile') or {}).get('name', '')
                     for c in value.get('contacts') or []}
            for message in value.get('messages') or []:
                try:
                    parsed = _parse_message(message, names)
                except ValueError:
                    continue
                if parsed:
                    inbound.append(parsed)
            for status in value.get('statuses') or []:
                if status.get('id') and status.get('status'):
                    errors = status.get('errors') or [{}]
                    detail = errors[0].get('title') or errors[0].get('message') or ''
                    statuses.append(StatusUpdate(status['id'], status['status'], str(detail)[:300]))
    return inbound, statuses


# ─── Giden ───────────────────────────────────────────────────────────────────
# Kurucular yalnız İÇERİĞİ üretir; alıcı gönderim anında `envelope` ile eklenir.
# Böylece örnek ekiplerin numarası yokken de içerik kuralları (buton sayısı,
# başlık uzunluğu) doğrulanır ve kayıtta ham numara tekrar tekrar durmaz.


def _check_body(body: str) -> str:
    if not body or len(body) > BODY_MAX:
        raise ValueError(f'Mesaj gövdesi 1–{BODY_MAX} karakter olmalı')
    return body


def envelope(to: str, content: dict) -> dict:
    if not E164.fullmatch(to or ''):
        raise ValueError('Alıcı E.164 biçiminde olmalı')
    return {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': to[1:], **content}


def text_content(body: str) -> dict:
    return {'type': 'text', 'text': {'body': _check_body(body), 'preview_url': True}}


def buttons_content(body: str, buttons: list[tuple[str, str]]) -> dict:
    if not 1 <= len(buttons) <= MAX_BUTTONS:
        raise ValueError(f'1–{MAX_BUTTONS} buton olmalı')
    for button_id, title in buttons:
        if not title or len(title) > BUTTON_TITLE_MAX:
            raise ValueError(f'Buton başlığı 1–{BUTTON_TITLE_MAX} karakter olmalı: {title!r}')
        if not button_id or len(button_id) > BUTTON_ID_MAX:
            raise ValueError('Buton kimliği geçersiz')
    return {'type': 'interactive', 'interactive': {
        'type': 'button',
        'body': {'text': _check_body(body)},
        'action': {'buttons': [{'type': 'reply', 'reply': {'id': i, 'title': t}} for i, t in buttons]},
    }}


def location_content(*, latitude: float, longitude: float, name: str, address: str) -> dict:
    return {'type': 'location', 'location': {
        'latitude': latitude, 'longitude': longitude, 'name': name[:100], 'address': address[:300]}}


def location_request_content(body: str) -> dict:
    """Müşterinin tek dokunuşla konum göndermesini sağlayan yerel WhatsApp isteği.
    Yalnız açık 24 saat penceresinde gönderilebilir (şablon olamaz)."""
    return {'type': 'interactive', 'interactive': {
        'type': 'location_request_message',
        'body': {'text': _check_body(body)},
        'action': {'name': 'send_location'},
    }}


def template_content(*, name: str, language: str, params: list[str],
                     quick_replies: list[str] | None = None) -> dict:
    """Onaylı şablon. Hızlı yanıt butonlarının kimliği gönderim anında verilir —
    böylece aynı şablon her iş için o işe özgü yanıt kimliği taşıyabilir."""
    if not name:
        raise ValueError('Şablon adı gerekli')
    components: list[dict] = []
    if params:
        components.append({'type': 'body', 'parameters': [{'type': 'text', 'text': str(p)[:1024]} for p in params]})
    for index, payload in enumerate(quick_replies or []):
        if not payload or len(payload) > BUTTON_ID_MAX:
            raise ValueError('Hızlı yanıt kimliği geçersiz')
        components.append({'type': 'button', 'sub_type': 'quick_reply', 'index': str(index),
                           'parameters': [{'type': 'payload', 'payload': payload}]})
    return {'type': 'template', 'template': {
        'name': name, 'language': {'code': language}, 'components': components}}


# ─── Gönderim ────────────────────────────────────────────────────────────────


class PermanentSendError(Exception):
    """Tekrar denemenin anlamı olmayan ret (geçersiz numara, şablon onaysız…)."""


def send(message: dict, *, client: httpx.Client | None = None) -> str:
    """Mesajı gönderir, sağlayıcı mesaj kimliğini döner.

    Dönen kimlik "Meta kabul etti" demektir, TESLİM EDİLDİ değil — teslim ve
    okundu bilgisi sonradan durum webhook'u ile gelir.
    4xx → PermanentSendError (tekrar denenmez); ağ/5xx → httpx hatası (outbox
    tekrar dener).
    """
    settings = get_settings()
    url = f'{GRAPH_URL}/{settings.automotive_whatsapp_phone_number_id}/messages'
    headers = {'Authorization': f'Bearer {settings.automotive_meta_access_token}'}
    owns_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        response = client.post(url, json=message, headers=headers)
    finally:
        if owns_client:
            client.close()
    if 400 <= response.status_code < 500:
        try:
            detail = response.json().get('error', {}).get('message', '')
        except ValueError:
            detail = ''
        raise PermanentSendError(f'{response.status_code} {detail}'[:300])
    response.raise_for_status()
    messages = response.json().get('messages') or [{}]
    provider_id = messages[0].get('id')
    if not provider_id:
        raise PermanentSendError('Sağlayıcı mesaj kimliği dönmedi')
    return provider_id
