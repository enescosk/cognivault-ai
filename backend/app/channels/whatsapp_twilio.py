"""Twilio WhatsApp — mesaj gönderimi (REST API).

Twilio'da WhatsApp adresleri `whatsapp:+90...` biçimindedir. Dönen `SID`
"Twilio kabul etti" demektir, TESLİM EDİLDİ değil; teslim durumu sonradan
status callback ile gelir.

24 saat kuralı Twilio'da da geçerlidir (WhatsApp'ın kuralı): pencere
kapalıyken serbest metin gitmez, onaylı içerik şablonu gerekir.
"""
from __future__ import annotations

import json
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
    if not body or len(body) > BODY_MAX:
        raise PermanentSendError(f'Mesaj 1–{BODY_MAX} karakter olmalı')
    return _post({'To': address(to), 'From': address(from_), 'Body': body}, account_sid=account_sid,
                 auth_token=auth_token, status_callback=status_callback, client=client)


def send_content(*, to: str, from_: str, content_sid: str, variables: dict[str, str], account_sid: str,
                 auth_token: str, status_callback: str | None = None, client: httpx.Client | None = None) -> str:
    """Onaylı içerik şablonu (Content API) gönderir — 24 saat penceresi kapalıyken
    gidebilen tek biçim. Hızlı yanıt düğmeleri şablonun kendisinde tanımlıdır."""
    if not content_sid:
        raise PermanentSendError('Twilio içerik şablonu (ContentSid) tanımlı değil')
    form = {'To': address(to), 'From': address(from_), 'ContentSid': content_sid,
            'ContentVariables': json.dumps(variables, ensure_ascii=False)}
    return _post(form, account_sid=account_sid, auth_token=auth_token,
                 status_callback=status_callback, client=client)


def _post(form: dict, *, account_sid: str, auth_token: str, status_callback: str | None,
          client: httpx.Client | None) -> str:
    if not account_sid or not auth_token:
        raise PermanentSendError('Twilio hesap bilgisi tanımlı değil')
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
