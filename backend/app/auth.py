"""
auth.py — ระบบผู้ใช้ (email/password จริง + OAuth Google/Facebook)
- รหัสผ่าน: PBKDF2-SHA256 (stdlib) ไม่เก็บ plain
- session: token ลายเซ็น HMAC-SHA256 (JWT-like) เก็บใน httpOnly cookie
- OAuth: authorization-code flow (ใช้ได้เมื่อตั้ง client id/secret)
fail-closed: ไม่มี secret = ออก token ไม่ได้ / OAuth ไม่เปิดให้ใช้
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

from . import db
from .config import get_settings

PBKDF2_ITER = 240_000
SESSION_TTL = 7 * 24 * 3600  # 7 วัน
COOKIE = "session"


# ---------- password ----------
def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, PBKDF2_ITER)
    return f"pbkdf2_sha256${PBKDF2_ITER}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, iters, salt_b64, dk_b64 = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except Exception:  # noqa
        return False


# ---------- session token (HMAC signed) ----------
def _secret() -> bytes:
    s = get_settings()
    sec = (s.AUTH_SECRET or s.SECURITY_KEY or "").strip()
    if not sec:
        raise RuntimeError("AUTH_SECRET/SECURITY_KEY ไม่ได้ตั้งค่า — ออก session token ไม่ได้ (fail-closed)")
    return sec.encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_session(user: dict) -> str:
    payload = {"uid": user["id"], "email": user.get("email"), "name": user.get("name"),
               "role": user.get("role", "user"), "exp": int(time.time()) + SESSION_TTL}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_session(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    try:
        expect = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    except RuntimeError:
        return None
    if not hmac.compare_digest(expect, sig):
        return None
    try:
        payload = json.loads(_unb64(body))
    except Exception:  # noqa
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def new_state() -> str:
    return secrets.token_urlsafe(16)


# ---------- users ----------
def ensure_users_table():
    db.execute("""CREATE TABLE IF NOT EXISTS users(
        id BIGSERIAL PRIMARY KEY, email TEXT UNIQUE, name TEXT,
        password_hash TEXT, provider TEXT DEFAULT 'password', provider_id TEXT,
        role TEXT DEFAULT 'user', created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def get_by_email(email: str):
    rows = db.query("SELECT * FROM users WHERE lower(email)=lower(%s)", (email,))
    return rows[0] if rows else None


def get_by_id(uid: int):
    rows = db.query("SELECT * FROM users WHERE id=%s", (uid,))
    return rows[0] if rows else None


def update_name(uid: int, name: str):
    name = (name or "").strip()
    if not name:
        raise ValueError("ชื่อต้องไม่ว่าง")
    db.execute("UPDATE users SET name=%s WHERE id=%s", (name, uid))


def change_password(uid: int, old: str, new: str):
    u = get_by_id(uid)
    if not u:
        raise ValueError("ไม่พบบัญชีผู้ใช้")
    if not u.get("password_hash"):
        raise ValueError("บัญชีนี้เข้าสู่ระบบด้วย Google/Facebook จึงไม่มีรหัสผ่านให้เปลี่ยน")
    if not verify_password(old or "", u["password_hash"]):
        raise ValueError("รหัสผ่านเดิมไม่ถูกต้อง")
    if len(new or "") < 8:
        raise ValueError("รหัสผ่านใหม่ต้องมีอย่างน้อย 8 ตัวอักษร")
    db.execute("UPDATE users SET password_hash=%s WHERE id=%s", (hash_password(new), uid))
    return True


def get_by_provider(provider: str, pid: str):
    rows = db.query("SELECT * FROM users WHERE provider=%s AND provider_id=%s", (provider, pid))
    return rows[0] if rows else None


def register_password(email: str, name: str, password: str) -> dict:
    ensure_users_table()
    if get_by_email(email):
        raise ValueError("อีเมลนี้ถูกใช้แล้ว")
    db.execute("INSERT INTO users(email,name,password_hash,provider) VALUES(%s,%s,%s,'password')",
               (email.strip(), name.strip(), hash_password(password)))
    return get_by_email(email)


def login_password(email: str, password: str):
    ensure_users_table()
    u = get_by_email(email)
    if not u or not u.get("password_hash") or not verify_password(password, u["password_hash"]):
        return None
    return u


def upsert_oauth(provider: str, pid: str, email: str, name: str) -> dict:
    ensure_users_table()
    u = get_by_provider(provider, pid) or (get_by_email(email) if email else None)
    if u:
        db.execute("UPDATE users SET name=COALESCE(NULLIF(%s,''),name), provider=%s, provider_id=%s WHERE id=%s",
                   (name, provider, pid, u["id"]))
        return db.query("SELECT * FROM users WHERE id=%s", (u["id"],))[0]
    db.execute("INSERT INTO users(email,name,provider,provider_id) VALUES(%s,%s,%s,%s)",
               (email, name, provider, pid))
    return get_by_provider(provider, pid)


# ---------- OAuth ----------
def oauth_configured(provider: str) -> bool:
    s = get_settings()
    return bool(getattr(s, f"{provider.upper()}_CLIENT_ID", "") and getattr(s, f"{provider.upper()}_CLIENT_SECRET", ""))


def authorize_url(provider: str, state: str) -> str:
    s = get_settings()
    base = s.REDIRECT_BASE.rstrip("/")
    ru = f"{base}/api/auth/{provider}/callback"
    if provider == "google":
        q = urlencode({"client_id": s.GOOGLE_CLIENT_ID, "redirect_uri": ru, "response_type": "code",
                       "scope": "openid email profile", "state": state, "access_type": "online"})
        return "https://accounts.google.com/o/oauth2/v2/auth?" + q
    if provider == "facebook":
        q = urlencode({"client_id": s.FACEBOOK_CLIENT_ID, "redirect_uri": ru,
                       "scope": "email,public_profile", "state": state})
        return "https://www.facebook.com/v21.0/dialog/oauth?" + q
    raise ValueError("unknown provider")


async def exchange_google(code: str) -> dict:
    s = get_settings()
    base = s.REDIRECT_BASE.rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": s.GOOGLE_CLIENT_ID, "client_secret": s.GOOGLE_CLIENT_SECRET,
            "redirect_uri": f"{base}/api/auth/google/callback", "grant_type": "authorization_code"})
        tok = r.json().get("access_token")
        if not tok:
            raise ValueError("Google token exchange ล้มเหลว")
        p = await c.get("https://openidconnect.googleapis.com/v1/userinfo",
                        headers={"Authorization": f"Bearer {tok}"})
        d = p.json()
    return {"pid": d.get("sub"), "email": d.get("email"), "name": d.get("name")}


async def exchange_facebook(code: str) -> dict:
    s = get_settings()
    base = s.REDIRECT_BASE.rstrip("/")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get("https://www.facebook.com/v21.0/oauth/access_token", params={
            "client_id": s.FACEBOOK_CLIENT_ID, "client_secret": s.FACEBOOK_CLIENT_SECRET,
            "redirect_uri": f"{base}/api/auth/facebook/callback", "code": code})
        tok = r.json().get("access_token")
        if not tok:
            raise ValueError("Facebook token exchange ล้มเหลว")
        p = await c.get("https://graph.facebook.com/v21.0/me",
                        params={"fields": "id,name,email", "access_token": tok})
        d = p.json()
    return {"pid": d.get("id"), "email": d.get("email"), "name": d.get("name")}
