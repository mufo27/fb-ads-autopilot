"""
User-supplied credentials store — ผู้ใช้กรอก key/token เองผ่านหน้าเว็บ
เก็บในตาราง app_credentials (DB) และ override ค่าที่อ่านจาก env ตอน runtime
- ไม่คืนค่า secret กลับออกไปตรงๆ (mask เหลือ 4 ตัวท้าย)
- secret ไม่ถูก log / ไม่ hardcode ในโค้ด
"""
from . import db
from . import security
from .config import get_settings

# ฟิลด์ที่ให้ผู้ใช้กรอกได้
FIELDS = {
    "META_APP_ID": "Meta App ID",
    "META_APP_SECRET": "Meta App Secret",
    "META_AD_ACCOUNT_ID": "Ad Account ID",
    "META_PAGE_ID": "Page ID",
    "META_PAGE_ACCESS_TOKEN": "Page Access Token",
    "META_MARKETING_TOKEN": "Marketing / System User Token",
    "AI_PROVIDER": "AI Provider",
    "AI_API_KEY": "AI API Key",
    "AI_MODEL": "AI Model",
    "AI_BASE_URL": "AI Base URL",
}
# ฟิลด์ความลับ = mask ไม่โชว์ค่าเต็ม
SECRET = {"META_APP_SECRET", "META_PAGE_ACCESS_TOKEN", "META_MARKETING_TOKEN", "AI_API_KEY"}


def ensure_table():
    db.execute(
        """CREATE TABLE IF NOT EXISTS app_credentials (
               name TEXT PRIMARY KEY,
               value TEXT NOT NULL,
               updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
    )


def save(mapping: dict) -> int:
    """อัปsert เฉพาะ key ที่รู้จักและมีการพิมพ์ค่ามา (ค่าว่าง = ไม่ทับของเดิม)"""
    ensure_table()
    n = 0
    for k, v in (mapping or {}).items():
        if k in FIELDS and v is not None and str(v).strip() != "":
            raw = str(v).strip()
            # S1: เข้ารหัสค่าลับก่อนลง DB เสมอ (ไม่มี SECURITY_KEY = SecurityError → fail-closed)
            stored = security.encrypt(raw) if k in SECRET else raw
            db.execute(
                """INSERT INTO app_credentials(name,value,updated_at)
                   VALUES (%s,%s,now())
                   ON CONFLICT(name) DO UPDATE SET value=excluded.value, updated_at=now()""",
                (k, stored),
            )
            n += 1
    apply_to_settings()
    return n


def load_all() -> dict:
    """คืนค่า plaintext (ถอดรหัส secret ให้แล้ว) สำหรับใช้ใน runtime"""
    ensure_table()
    out = {}
    for r in db.query("SELECT name,value FROM app_credentials"):
        name, val = r["name"], r["value"]
        if name in SECRET:
            val = security.decrypt(val, fail_open=True)  # ถอดไม่ได้ = ถือว่ายังไม่ได้ใส่ (ปลอดภัยกว่า)
        out[name] = val
    return out


def apply_to_settings():
    """ดันค่าที่ผู้ใช้ใส่ (จาก DB) ทับ instance Settings ที่ cache ไว้ → meta_client/AI ใช้ทันที"""
    s = get_settings()
    for k, v in load_all().items():
        if hasattr(s, k):
            setattr(s, k, v)


def _mask(name: str, value: str) -> str:
    if name not in SECRET:
        return value
    if not value:
        return ""
    tail = value[-4:]
    return "•" * 8 + tail


def status() -> dict:
    """คืนค่าที่ mask แล้ว + ว่าเซ็ตหรือยัง — ใช้แสดงในหน้า Connect Keys (ไม่มีค่าลับหลุด)"""
    s = get_settings()
    out = {}
    for k, label in FIELDS.items():
        raw = getattr(s, k, "") or ""
        out[k] = {"label": label, "secret": k in SECRET, "is_set": bool(raw),
                  "preview": _mask(k, raw)}
    return out
