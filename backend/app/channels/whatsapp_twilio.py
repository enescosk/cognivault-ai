"""Twilio WhatsApp — mesaj gönderimi (REST API).

Twilio'da WhatsApp adresleri `whatsapp:+90...` biçimindedir. Dönen `SID`
"Twilio kabul etti" demektir, TESLİM EDİLDİ değil; teslim durumu sonradan
status callback ile gelir.

24 saat kuralı Twilio'da da geçerlidir (WhatsApp'ın kuralı): pencere
kapalıyken serbest metin gitmez, onaylı içerik şablonu gerekir.
"""
from __future__ import annotations

import re

import httpx

from app.channels.whatsapp_meta import PermanentSendError

API_URL = 'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json'
ADDRESS = re.compile(r'whatsapp:\+[1-9]\d{7,14}')
BODY_MAX = 1600


def address(phone: str) -> str:
    value = phone if phone.startswith('whatsapp:') else f'whatsapp:{phone}'
    if not ADDRESS.fullmatch(value):
        raise ValueError('Geçersiz WhatsApp adresi')
    return value


def send_text(*, to: str, body: str, from_: str, account_sid: str, auth_token: str,
              status_callback: str | None = None, client: httpx.Client | None = None) -> str:
    """Serbest metin gönderir, Twilio mesaj SID'ini döner.

    4xx → PermanentSendError (tekrar denenmez); ağ/5xx → httpx hatası (outbox
    tekrar dener).
    """
    if not account_sid or not auth_token:
        raise PermanentSendError('Twilio hesap bilgisi tanımlı değil')
    if not body or len(body) > BODY_MAX:
        raise PermanentSendError(f'Mesaj 1–{BODY_MAX} karakter olmalı')
    form = {'To': address(to), 'From': address(from_), 'Body': body}
    if status_callback:
        form['StatusCallback'] = status_callback
    owns_client = client is None
    client = client or httpx.Client(timeout=10)
    try:
        response = client.post(API_URL.format(sid=account_sid), data=form, auth=(account_sid, auth_token))
    finally:
        if owns_client:
            client.close()
    if 400 <= response.status_code < 500:
        try:
            detail = response.json().get('message', '')
        except ValueError:
            detail = ''
        raise PermanentSendError(f'{response.status_code} {detail}'[:300])
    response.raise_for_status()
    sid = response.json().get('sid')
    if not sid:
        raise PermanentSendError('Twilio mesaj kimliği dönmedi')
    return sid
