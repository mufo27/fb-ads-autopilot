"""
Test ชั้น logic เพิ่มเติม: rate-limit, meta insight parser, dry-run guard
รัน:  cd backend && python ../scripts/test_engine.py
"""
import sys, types, os, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

cfg = types.SimpleNamespace(
    META_MARKETING_TOKEN="EAtoken", META_PAGE_ACCESS_TOKEN="", META_AD_ACCOUNT_ID="act_1",
    AI_PROVIDER="ollama", AI_API_KEY="", DATABASE_URL="", LOG_LEVEL="INFO",
    SYSTEM_MAX_DAILY_CAP=5000, SECURITY_KEY="",
)
fake_cfg = types.ModuleType("app.config")
fake_cfg.get_settings = lambda: cfg
sys.modules["app.config"] = fake_cfg
fake_db = types.ModuleType("app.db")
fake_db.query = lambda sql, params=None: []
fake_db.execute = lambda sql, params=None: 1
sys.modules["app.db"] = fake_db

res = []
def check(name, cond):
    res.append((name, cond)); print(("PASS" if cond else "FAIL"), "·", name)

# ---------- ratelimit ----------
from app import ratelimit
ratelimit.reset()
ok_seq = [ratelimit.allow("k1", 3, 60)[0] for _ in range(5)]
check("RL: 3 ครั้งแรกผ่าน", ok_seq[:3] == [True, True, True])
check("RL: ครั้งที่ 4-5 ถูกบล็อก", ok_seq[3] is False and ok_seq[4] is False)
allowed, retry = ratelimit.allow("k1", 3, 60)
check("RL: คืน retry_after > 0 เมื่อเกิน", retry >= 1)
check("RL: key คนละชุดไม่กระทบกัน", ratelimit.allow("k2", 1, 60)[0] is True)

# ---------- sync.parse_insight ----------
from app import sync
row = {
    "id": "120", "name": "ป้ายยา powerbank", "daily_budget": "25000",  # cents = 250 บาท
    "spend": "180.50", "impressions": "1000", "clicks": "35",
    "actions": [{"action_type": "purchase", "value": "12"}, {"action_type": "link_click", "value": "999"}],
    "action_values": [{"action_type": "offsite_conversion.fb_pixel_purchase", "value": "540.00"}],
}
m = sync.parse_insight(row)
check("PARSE: meta id + name", m["meta_adset_id"] == "120" and "powerbank" in m["name"])
check("PARSE: daily_budget cents→บาท (25000 → 250)", m["daily_budget"] == 250.0)
check("PARSE: spend = 180.5", m["spend"] == 180.5)
check("PARSE: conversions นับเฉพาะ purchase (12)", m["conversions"] == 12)
check("PARSE: revenue จาก action_values (540)", m["revenue"] == 540.0)
m2 = sync.parse_insight({"id": "9"})  # ค่าขาดครบ
check("PARSE: row ขาดข้อมูล = ไม่ crash, ค่า 0", m2["spend"] == 0 and m2["conversions"] == 0 and m2["daily_budget"] == 0)

# ---------- ai_engine dry-run guard (ห้ามยิง Meta ตอน dry-run) ----------
import app.ai_engine as eng
calls = []
async def fake_pause(aid): calls.append(("pause", aid)); return {"success": True}
async def fake_budget(aid, cents): calls.append(("budget", aid, cents)); return {"success": True}
eng.meta_client.pause_adset = fake_pause
eng.meta_client.update_adset_budget = fake_budget
# stub db ให้คืน meta id และรับ update
eng.db.query = lambda sql, params=None: ([{"meta_adset_id": "777"}] if "meta_adset_id" in sql else [{"revenue": 0, "spend": 0}])
eng.db.execute = lambda sql, params=None: 1
from app.guardrails import ProposedAction

def run(coro): return asyncio.run(coro)
calls.clear()
pushed_dry = run(eng._apply(ProposedAction(action="PAUSE", ad_set_id=5), dry=True))
check("DRY-RUN: PAUSE ไม่ยิง Meta", pushed_dry is False and len(calls) == 0)
calls.clear()
pushed_live = run(eng._apply(ProposedAction(action="PAUSE", ad_set_id=5), dry=False))
check("LIVE: PAUSE ยิง Meta จริง", pushed_live is True and ("pause", "777") in calls)
calls.clear()
run(eng._apply(ProposedAction(action="RAISE_BUDGET", ad_set_id=5, new_daily_budget=300), dry=False))
check("LIVE: งบ ×100 เป็น cents ตอนยิง Meta", ("budget", "777", 30000) in calls)

passed = sum(1 for _, c in res if c)
print(f"\n{passed}/{len(res)} engine tests passed")
sys.exit(0 if passed == len(res) else 1)
