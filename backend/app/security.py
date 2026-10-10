"""
security.py — แกนความปลอดภัยของระบบ (fail-closed เป็นดีฟอลต์)

หลักที่ยึด (invariants):
  S1  ความลับต้องถูกเข้ารหัสก่อนวางบน disk/DB เสมอ (encryption-at-rest ด้วย Fernet/AES)
      ไม่มี SECURITY_KEY = ปฏิเสธไม่เก็บ secret (ไม่ fallback เป็น plaintext)
  S2  ทุก endpoint ที่ "สั่งใช้เงิน / อ่าน-เขียน key / แก้กรอบเหล็ก" ต้องยืนยันตัวตน
      ไม่มี ADMIN_TOKEN = ล็อกทุก endpoint (ปฏิเสธ ไม่ใช่ปล่อยผ่าน)
  S3  AI ไม่มีวันแตะเงินโดยตรง — ข้อเสนอสั้นๆ ต้องผ่าน guardrail เสมอ (บังคับในโค้ด ไม่ใช่ความเต็มใจ)
  S4  ค่าลับต้องถูก redact ในทุก response/log (ไม่มีทางหลุดออก)
  S5  มี kill switch ที่คนกดได้ทันทีเพื่อปิดการทำงานของ AI
  S6  hard cap รายวันถูกคุมด้วยเพดานสูงสุด (SYSTEM_MAX_DAILY_CAP) ต่อให้มี token ก็ขยายเองมั่วไม่ได้
"""
import base64
import hashlib
import hmac
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class SecurityError(RuntimeError):
    """fail-closed: ไม่ปลอดภัย = ยกเลิกการทำงาน"""


# ---- S1: Encryption at rest --------------------------------------------------
@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = (get_settings().SECURITY_KEY or "").strip()
    if not key:
        raise SecurityError(
            "SECURITY_KEY ยังไม่ได้ตั้งค่า — ระบบปฏิเสธการเก็บ secret (fail-closed). "
            "สร้างด้วย: python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return ""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str, *, fail_open: bool = False) -> str:
    """ค่าที่เข้ารหัสไว้ -> plaintext; ถ้าถอดไม่สำเร็จ (key เปลี่ยน/ค่าเก่า) = คืน '' (视作 unset)"""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        if fail_open:
            return ""
        raise SecurityError("ถอดรหัส secret ไม่สำเร็จ (SECURITY_KEY เปลี่ยน?) — ปฏิเสธการใช้ค่านี้")


# ---- S2: Admin auth (constant-time, PBKDF2 hash at rest) ---------------------
def hash_admin_token(token: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", token.encode(), salt, 240_000)
    return f"pbkdf2_sha256$240000${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_admin_token(token: str) -> bool:
    s = get_settings()
    expected = (s.ADMIN_TOKEN or "").strip()
    stored_hash = (s.ADMIN_TOKEN_HASH or "").strip()
    if not expected and not stored_hash:
        # fail-closed: ไม่มี admin ที่ตั้งค่าไว้ = ไม่มีใครได้สิทธิ์
        return False
    if not token:
        return False
    if stored_hash:
        try:
            _, iters, salt_b64, dk_b64 = stored_hash.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", token.encode(), base64.b64decode(salt_b64), int(iters))
            return hmac.compare_digest(dk, base64.b64decode(dk_b64))
        except Exception:  # noqa
            return False
    return hmac.compare_digest(token, expected)


def auth_enabled() -> bool:
    s = get_settings()
    return bool((s.ADMIN_TOKEN or "").strip() or (s.ADMIN_TOKEN_HASH or "").strip())


# ---- S4: Redaction -----------------------------------------------------------
SENSITIVE_KEYS = {
    "META_APP_SECRET", "META_PAGE_ACCESS_TOKEN", "META_MARKETING_TOKEN",
    "AI_API_KEY", "SECURITY_KEY", "ADMIN_TOKEN", "access_token", "password",
}


def mask_value(value: str) -> str:
    if not value:
        return ""
    return "•" * 8 + value[-4:] if len(value) > 4 else "••••"


def redact(obj):
    """คืน deepcopy ที่ค่าของคีย์อ่อนไหวถูก mask — ใช้ก่อน log/return"""
    if isinstance(obj, dict):
        return {k: (mask_value(v) if (k in SENSITIVE_KEYS and isinstance(v, str)) else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


# ---- S6: Cap ceiling ---------------------------------------------------------
def clamp_daily_cap(requested: float) -> float:
    ceiling = get_settings().SYSTEM_MAX_DAILY_CAP
    return min(float(requested), float(ceiling))


# ---- S5: Kill switch (คนกดปิด AI ได้ทันที) -----------------------------------
_STATE = {"killed": False}


def is_killed() -> bool:
    return _STATE["killed"]


def set_killed(flag: bool):
    _STATE["killed"] = bool(flag)
