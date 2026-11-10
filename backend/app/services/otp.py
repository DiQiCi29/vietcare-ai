"""Customer login OTP: Twilio Verify when configured, otherwise an in-memory demo provider.

Twilio trial accounts can only text verified numbers in the sign-up country, so the
demo provider keeps the app usable for classes, tests and an expired trial.
"""
import hmac
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException

from backend.app.core.config import settings

logger = logging.getLogger(__name__)
VERIFY_URL = 'https://verify.twilio.com/v2/Services/{sid}/{action}'

# Twilio error codes worth translating for the customer; others get a generic message.
TWILIO_ERRORS = {
    21608: 'Tài khoản Twilio dùng thử chỉ gửi được tới số đã xác minh trong Twilio Console.',
    21211: 'Số điện thoại không hợp lệ.',
    60200: 'Số điện thoại không hợp lệ.',
    60203: 'Bạn đã yêu cầu mã quá nhiều lần. Vui lòng thử lại sau ít phút.',
    60205: 'Số điện thoại này không nhận được SMS.',
    60410: 'Số điện thoại tạm thời bị chặn gửi mã. Vui lòng thử lại sau.',
}


@dataclass
class _DemoCode:
    code: str
    expires_at: float
    attempts: int = 0


_lock = threading.Lock()
_demo_codes: dict[str, _DemoCode] = {}
_last_sent: dict[str, float] = {}


def to_e164(phone):
    """Vietnamese local numbers (0905...) become +84905...; other inputs must already be E.164."""
    digits = re.sub(r'[\s.-]', '', str(phone or ''))
    if re.fullmatch(r'0\d{9}', digits):
        return '+84' + digits[1:]
    if re.fullmatch(r'84\d{9}', digits):
        return '+' + digits
    if re.fullmatch(r'\+\d{8,15}', digits):
        return digits
    raise HTTPException(422, 'Số điện thoại không hợp lệ')


def twilio_enabled():
    return all((settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN, settings.TWILIO_VERIFY_SERVICE_SID))


def _twilio(action, data):
    sid = settings.TWILIO_VERIFY_SERVICE_SID
    if not re.fullmatch(r'VA[0-9a-fA-F]{32}', sid):
        raise HTTPException(500, 'TWILIO_VERIFY_SERVICE_SID không hợp lệ (phải bắt đầu bằng VA)')
    try:
        response = httpx.post(VERIFY_URL.format(sid=sid, action=action), data=data,
                              auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
                              timeout=httpx.Timeout(10, connect=4))
    except httpx.HTTPError:
        logger.warning('Twilio Verify unreachable')
        raise HTTPException(503, 'Không kết nối được dịch vụ gửi mã OTP, vui lòng thử lại')
    if response.status_code < 400:
        return response.json()
    try:
        code = response.json().get('code')
    except ValueError:
        code = None
    if action == 'VerificationCheck' and response.status_code == 404:
        # Twilio deletes a verification once it is approved, expired or out of attempts.
        raise HTTPException(400, 'Mã OTP đã hết hạn, vui lòng yêu cầu mã mới')
    logger.warning('Twilio Verify %s failed: HTTP %s code=%s', action, response.status_code, code)
    if response.status_code == 401:
        raise HTTPException(500, 'Sai TWILIO_ACCOUNT_SID hoặc TWILIO_AUTH_TOKEN')
    raise HTTPException(400 if code in TWILIO_ERRORS else 502,
                        TWILIO_ERRORS.get(code, 'Dịch vụ OTP từ chối yêu cầu, vui lòng thử lại sau'))


def send_code(phone):
    """Send a code; returns the response body. `demo_code` is only present in demo mode."""
    target = to_e164(phone)
    now = time.monotonic()
    with _lock:
        wait = settings.OTP_RESEND_SECONDS - (now - _last_sent.get(target, -1e9))
        if wait > 0:
            raise HTTPException(429, f'Vui lòng chờ {int(wait) + 1} giây trước khi gửi lại mã')
        _last_sent[target] = now
    result = {'expires_in': settings.OTP_TTL_SECONDS, 'resend_after': settings.OTP_RESEND_SECONDS}
    if twilio_enabled():
        try:
            _twilio('Verifications', {'To': target, 'Channel': 'sms', 'Locale': 'vi'})
        except HTTPException:
            with _lock:
                _last_sent.pop(target, None)  # A failed send must not block a retry.
            raise
        return {**result, 'mode': 'twilio', 'message': 'Đã gửi mã OTP qua SMS'}

    code = f'{secrets.randbelow(10 ** 6):06d}'
    with _lock:
        _demo_codes[target] = _DemoCode(code, now + settings.OTP_TTL_SECONDS)
    logger.warning('[OTP DEMO] Login code for %s: %s', target, code)  # ASCII: Windows consoles mangle Vietnamese.
    return {**result, 'mode': 'demo', 'demo_code': code,
            'message': 'Chế độ demo (chưa cấu hình Twilio): mã OTP hiển thị trên màn hình'}


def check_code(phone, code):
    target = to_e164(phone)
    code = str(code or '').strip()
    if not re.fullmatch(r'\d{4,10}', code):
        raise HTTPException(400, 'Mã OTP không chính xác')
    if twilio_enabled():
        if _twilio('VerificationCheck', {'To': target, 'Code': code}).get('status') != 'approved':
            raise HTTPException(400, 'Mã OTP không chính xác')
        return
    with _lock:
        entry = _demo_codes.get(target)
        if not entry or time.monotonic() > entry.expires_at:
            _demo_codes.pop(target, None)
            raise HTTPException(400, 'Mã OTP đã hết hạn, vui lòng yêu cầu mã mới')
        entry.attempts += 1
        if not hmac.compare_digest(entry.code, code):
            if entry.attempts >= settings.OTP_MAX_ATTEMPTS:
                _demo_codes.pop(target, None)
                raise HTTPException(400, 'Nhập sai quá nhiều lần, vui lòng yêu cầu mã mới')
            raise HTTPException(400, 'Mã OTP không chính xác')
        del _demo_codes[target]  # One-time use.


def reset_demo_state():
    with _lock:
        _demo_codes.clear()
        _last_sent.clear()
