"""
Test การเก็บ key ที่ User ใส่เอง — ไม่ต้องมี DB/Docker
รัน:  cd backend && python ../scripts/test_credentials.py
พิสูจน์: key เข้า DB, override config จริง, และ secret ถูก mask (ค่าลับไม่หลุด)
"""
import sys, types, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from cryptography.fernet import Fernet

# ---- fake in-memory db ------------------------------------------------------
_store = {}
fake_db = types.ModuleType("app.db")
def _execute(sql, params=None):
    if "INSERT INTO app_credentials" in sql and params:
        _store[params[0]] = params[1]
    return 1
def _query(sql, params=None):
    if "SELECT name,value" in sql:
        return [{"name": k, "value": v} for k, v in _store.items()]
    return []
fake_db.execute = _execute; fake_db.query = _query
sys.modules["app.db"] = fake_db

# ---- fake settings singleton (mutable) --------------------------------------
FIELDS = ["META_APP_ID","META_APP_SECRET","META_AD_ACCOUNT_ID","META_PAGE_ID",
          "META_PAGE_ACCESS_TOKEN","META_MARKETING_TOKEN","AI_PROVIDER","AI_API_KEY",
          "AI_MODEL","AI_BASE_URL","SECURITY_KEY"]
settings = types.SimpleNamespace(**{f: "" for f in FIELDS})
settings.AI_PROVIDER = "openai"; settings.AI_MODEL = "gpt-4o-mini"
settings.SECURITY_KEY = Fernet.generate_key().decode()   # ตั้งคีย์เข้ารหัส (S1)
fake_cfg = types.ModuleType("app.config")
fake_cfg.get_settings = lambda: settings
sys.modules["app.config"] = fake_cfg

import app.credentials as cr
import app.security as sec
cr.db = fake_db

tok = "EAAb123SECRETVALUE9f3d"
saved = cr.save({"META_APP_ID": "1077740761537101",
                 "META_MARKETING_TOKEN": tok,
                 "AI_API_KEY": "sk-proj-abcdefXYZ123",
                 "META_PAGE_ID": "   "})   # ค่าว่าง -> ต้องไม่ถูกบันทึก
res = []
def check(name, cond):
    res.append((name, cond)); print(("PASS" if cond else "FAIL"), "·", name)

check("save ทับเฉพาะค่าที่มี content (page id ว่างไม่เข้า DB)",
      "META_PAGE_ID" not in _store)
check("S1: token ใน DB เป็น ciphertext ไม่ใช่ plaintext", _store["META_MARKETING_TOKEN"] != tok and "EAAb" not in _store["META_MARKETING_TOKEN"])
check("S1: AI key ใน DB เป็น ciphertext", "abcdef" not in _store["AI_API_KEY"])
check("S1: App ID (ไม่ใช่ secret) เก็บ plaintext", _store["META_APP_ID"] == "1077740761537101")
check("S1: ถอดรหัสกลับได้ค่าเดิมผ่าน load_all", cr.load_all()["META_MARKETING_TOKEN"] == tok)
check("override เข้า settings เป็น plaintext", settings.META_MARKETING_TOKEN == tok)
check("App ID override", settings.META_APP_ID == "1077740761537101")

st = cr.status()
check("App ID ไม่ใช่ secret -> โชว์เต็ม", st["META_APP_ID"]["secret"] is False and st["META_APP_ID"]["preview"] == "1077740761537101")
check("token ถูก mark secret + is_set", st["META_MARKETING_TOKEN"]["secret"] is True and st["META_MARKETING_TOKEN"]["is_set"] is True)
check("preview token ไม่เผยค่าลับ (ไม่มี substring จริง)", tok not in st["META_MARKETING_TOKEN"]["preview"])
check("preview token โชว์แค่ 4 ตัวท้าย + mask", st["META_MARKETING_TOKEN"]["preview"].endswith(tok[-4:]) and "•" in st["META_MARKETING_TOKEN"]["preview"])

# save ค่าใหม่ทับของเดิม + ค่าว่างไม่ลบของเดิม
cr.save({"META_APP_ID": "999", "META_MARKETING_TOKEN": ""})
check("ค่าว่างไม่ทับ token เดิม", settings.META_MARKETING_TOKEN == tok)
check("ค่าใหม่ทับ App ID เดิม", settings.META_APP_ID == "999")

# fail-closed: ไม่มี SECURITY_KEY = บันทึก secret ไม่ได้
settings.SECURITY_KEY = ""
sec._fernet.cache_clear()
try:
    cr.save({"META_MARKETING_TOKEN": "newsecret"})
    check("S1 fail-closed: ไม่มีคีย์ = โยน SecurityError", False)
except sec.SecurityError:
    check("S1 fail-closed: ไม่มีคีย์ = โยน SecurityError (ไม่เก็บ plaintext)", True)

passed = sum(1 for _, c in res if c)
print(f"\n{passed}/{len(res)} credential/encryption tests passed")
sys.exit(0 if passed == len(res) else 1)
