"""
Test แกนความปลอดภัย (S1–S6) — ไม่ต้องมี DB/FastAPI
รัน:  cd backend && python ../scripts/test_security.py
"""
import sys, types, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from cryptography.fernet import Fernet

cfg = types.SimpleNamespace(
    SECURITY_KEY=Fernet.generate_key().decode(), ADMIN_TOKEN="", ADMIN_TOKEN_HASH="",
    SYSTEM_MAX_DAILY_CAP=5000,
)
fake_cfg = types.ModuleType("app.config")
fake_cfg.get_settings = lambda: cfg
sys.modules["app.config"] = fake_cfg
sys.modules["app.db"] = types.ModuleType("app.db")   # security ไม่แตะ db

import app.security as sec

res = []
def check(name, cond):
    res.append((name, cond)); print(("PASS" if cond else "FAIL"), "·", name)
def raises(fn, exc):
    try:
        fn(); return False
    except exc:
        return True

# ---- S1: encryption at rest ----
ct = sec.encrypt("top-secret-token-ABC123")
check("S1: ciphertext != plaintext (ค่าลับไม่โผล่ใน disk)", ct != "top-secret-token-ABC123" and "ABC123" not in ct)
check("S1: round-trip ถูกต้อง", sec.decrypt(ct) == "top-secret-token-ABC123")
check("S1: decrypt ค่าเสีย = throw (fail-closed)", raises(lambda: sec.decrypt("garbage"), sec.SecurityError))
check("S1: decrypt ค่าเสีย + fail_open = คืน ''", sec.decrypt("garbage", fail_open=True) == "")
cfg.SECURITY_KEY = ""; sec._fernet.cache_clear()
check("S1: ไม่มีคีย์ = encrypt throw (ไม่เก็บ plaintext)", raises(lambda: sec.encrypt("x"), sec.SecurityError))
cfg.SECURITY_KEY = Fernet.generate_key().decode(); sec._fernet.cache_clear()

# ---- S2: admin auth (fail-closed) ----
check("S2: ไม่ตั้ง admin = auth_enabled False", sec.auth_enabled() is False)
check("S2: ไม่ตั้ง admin = verify ทุกกรณี False (fail-closed)", sec.verify_admin_token("") is False and sec.verify_admin_token("guess") is False)
cfg.ADMIN_TOKEN = "s3cr3t-passphrase"
check("S2: token ถูกต้อง -> True", sec.verify_admin_token("s3cr3t-passphrase") is True)
check("S2: token ผิด -> False", sec.verify_admin_token("wrong") is False)
check("S2: token ว่าง -> False", sec.verify_admin_token("") is False)
cfg.ADMIN_TOKEN = ""; cfg.ADMIN_TOKEN_HASH = sec.hash_admin_token("hashed-pass")
check("S2: ใช้ hash แทนค่าจริง -> ถูกต้อง True", sec.verify_admin_token("hashed-pass") is True)
check("S2: hash — ผิดเป็น False", sec.verify_admin_token("nope") is False)
cfg.ADMIN_TOKEN_HASH = ""

# ---- S4: redaction ----
r = sec.redact({"META_MARKETING_TOKEN": "EAABsecret9f3d", "AI_API_KEY": "sk-live-1234", "count": 3,
                "nested": {"access_token": "leakme123", "x": "ok"}})
check("S4: secret ถูก mask ใน nested dict (ปิดส่วนกลาง, เก็บ 4 ตัวท้าย)",
      "secret" not in str(r) and "leakme" not in str(r)
      and r["AI_API_KEY"].endswith("1234") and "live" not in r["AI_API_KEY"])
check("S4: ค่าไม่ลับคงเดิม", r["count"] == 3 and r["nested"]["x"] == "ok")
check("S4: mask เก็บ 4 ตัวท้าย", r["META_MARKETING_TOKEN"].endswith("9f3d"))

# ---- S5: kill switch ----
check("S5: default ไม่ killed", sec.is_killed() is False)
sec.set_killed(True); check("S5: set_killed(True)", sec.is_killed() is True)
sec.set_killed(False); check("S5: set_killed(False)", sec.is_killed() is False)

# ---- S6: cap ceiling ----
check("S6: clamp เกินเพดาน -> เพดาน", sec.clamp_daily_cap(999999) == 5000)
check("S6: clamp ต่ำกว่าเพดาน -> ค่าเดิม", sec.clamp_daily_cap(800) == 800)

passed = sum(1 for _, c in res if c)
print(f"\n{passed}/{len(res)} security tests passed")
sys.exit(0 if passed == len(res) else 1)
