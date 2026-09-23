"""Opt-in inbound phone -> company dispatcher bridge. Never dials arbitrary input."""
import re
from urllib.parse import parse_qs, urlparse
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import HTTPException, Request
from app.core.config import get_settings
from app.core.webhook_security import verify_twilio_signature


def verify_request(request: Request, raw: bytes) -> dict:
    s = get_settings()
    if not s.automotive_voice_enabled:
        raise HTTPException(503, 'Otomotiv telefon bağlantısı etkin değil.')
    number = r'\+[1-9]\d{7,14}'
    base = urlparse(s.automotive_webhook_base_url)
    if (not re.fullmatch(number, s.automotive_inbound_number)
        or not re.fullmatch(number, s.automotive_dispatch_number)
        or s.automotive_inbound_number == s.automotive_dispatch_number
        or base.scheme != 'https' or not base.netloc or base.path not in ('', '/')
        or base.query or base.fragment or base.username or not s.twilio_account_sid):
        raise HTTPException(503, 'Doğrulanmış hat, farklı hedef numara ve HTTPS origin gerekli.')
    if len(raw) > 16384:
        raise HTTPException(413, 'İstek çok büyük.')
    try:
        values = parse_qs(raw.decode('utf-8'), keep_blank_values=True)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(400, 'Geçersiz telefon isteği.') from None
    if any(len(v) != 1 for v in values.values()):
        raise HTTPException(400, 'Tekrarlanan form alanı.')
    fields = {k: v[0] for k, v in values.items()}
    # Exact configured URL, not attacker-controlled Host or proxy headers.
    url = s.automotive_webhook_base_url.rstrip('/') + request.url.path
    if request.url.query:
        url += '?' + request.url.query
    if not verify_twilio_signature(auth_token=s.twilio_auth_token, request_url=url,
                                   form_params=fields, signature_header=request.headers.get('X-Twilio-Signature')):
        raise HTTPException(401, 'Geçersiz telefon sağlayıcısı imzası.')
    if fields.get('AccountSid') != s.twilio_account_sid or fields.get('To') != s.automotive_inbound_number:
        raise HTTPException(403, 'Bu hesap veya numara otomotiv hattına bağlı değil.')
    return fields


def say(parent, text):
    SubElement(parent, 'Say', language='tr-TR', voice='alice').text = text


def _base_path() -> str:
    return get_settings().api_prefix + '/automotive/webhooks/voice'


def _gather(root, text: str, attempt: int) -> None:
    gather = SubElement(root, 'Gather', input='speech dtmf', language='tr-TR', numDigits='1',
                        speechTimeout='auto', timeout='7', method='POST',
                        action=f'{_base_path()}/gather?attempt={attempt}')
    say(gather, text)


def _dial(root) -> None:
    SubElement(SubElement(root, 'Dial', answerOnBridge='true', timeout='20',
                         action=_base_path() + '/transfer-status', method='POST'),
               'Number').text = get_settings().automotive_dispatch_number


def response(kind: str, fields: dict) -> str:
    settings = get_settings()
    root = Element('Response')
    if kind == 'incoming':
        _gather(root, f'{settings.automotive_brand} hattına hoş geldiniz. Ben dijital asistanınızım. '
                      'Size nasıl yardımcı olabilirim? Aracınızda ne olduğunu kısaca söyleyin; doğrudan '
                      'yardım ekibine bağlanmak için bir tuşlayabilirsiniz. Yaralanma, yangın veya yakın '
                      'tehlike varsa önce 112’yi arayın.', attempt=1)
        say(root, 'Yanıt alınamadı. Yardım talebiniz sürüyorsa lütfen yeniden arayın.')
    else:
        if fields.get('DialCallStatus') == 'completed':
            say(root, 'Görevlimizle görüşmeniz sona erdi. İyi günler dileriz.')
        else:
            say(root, 'Şu anda ekibe bağlantı kurulamadı. Lütfen tekrar arayın veya servisimizin WhatsApp hattından bize ulaşın. '
                      'Henüz çekici sevk edilmedi. Acil tehlikede 112’yi arayın.')
    return tostring(root, encoding='unicode')


def call_reply(outcome, *, attempt: int) -> str:
    """`roadside.handle_call` sonucunu TwiML'e çevirir.

    `outcome` None ise (gelen kanal sahibi tanımlı değil, iş açılamadı) arama
    DÜŞMEZ: arayan yine dispeçere aktarılır, yalnız iş kaydı açılmaz.
    """
    root = Element('Response')
    if outcome is None:
        say(root, 'Sizi yol yardım ekibimize bağlıyorum; görevlimiz konumunuzu ve ihtiyacınızı teyit edecek.')
        _dial(root)
    elif outcome.ask_again:
        _gather(root, outcome.say, attempt=attempt + 1)
        say(root, 'Sizi yol yardım ekibimize bağlıyorum.')
        _dial(root)
    else:
        say(root, outcome.say)
        _dial(root)
    return tostring(root, encoding='unicode')
