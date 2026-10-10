"""
Standalone test ของ guardrail rules — ไม่ต้องมี Postgres/Docker
รัน:  cd backend && python ../scripts/test_guardrails.py
พิสูจน์ว่า "กรอบเหล็ก" ดัก AI ได้จริงทุกข้อ
"""
import sys, types, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# ---- stub app.db และ app.config เพื่อ import app.guardrails เดี่ยวๆ ------------
fake_db = types.ModuleType("app.db")
LEARN = {"in_learning": False, "conversions": 999}
DUP = {"exists": False}
def _query(sql, params=None):
    if "in_learning" in sql and "conversions" in sql:
        return [dict(LEARN)]
    if "audience_sig" in sql or "content_sig" in sql:
        return [ {"id": 1} ] if DUP["exists"] else []
    return []
def _execute(sql, params=None):
    return 1
fake_db.query = _query
fake_db.execute = _execute
sys.modules["app.db"] = fake_db

fake_cfg_mod = types.ModuleType("app.config")
CFG = {"daily_hard_cap": 1000, "per_campaign_cap": 400, "velocity_window_min": 120,
       "velocity_max_pct": 30, "min_roas": 1.5, "learning_min_conv": 50, "dry_run": False}
fake_cfg_mod.get_settings = lambda: types.SimpleNamespace(LOG_LEVEL="INFO")
sys.modules["app.config"] = fake_cfg_mod

import app.guardrails as gr
gr._cfg = lambda: type("C", (), dict(CFG))()
spend = {"today": 0.0, "recent": 0.0}
gr._spend_today = lambda: spend["today"]
gr._spend_recent = lambda m: spend["recent"]
gr._audit = lambda *a, **k: None   # mute logging

def P(**kw): return gr.ProposedAction(**kw)

cases = []
def check(name, got, want):
    ok = got == want
    cases.append((name, want, got, ok))
    print(f"{'PASS' if ok else 'FAIL'} · {name}: verdict={got} rule={name and ''}")

# 1 เกินเพดานต่อกามเปญ
check("per-campaign cap",
      gr.check_proposed_action(P(action="RAISE_BUDGET", new_daily_budget=500)).result, gr.BLOCK)
# 2 push เกิน hard cap รายวัน
spend["today"] = 800
check("daily hard cap",
      gr.check_proposed_action(P(action="RAISE_BUDGET", new_daily_budget=400)).result, gr.BLOCK)
spend["today"] = 0
# 3 velocity เกิน
spend["recent"] = 400  # > 30% ของ 1000
check("spend velocity",
      gr.check_proposed_action(P(action="RAISE_BUDGET", new_daily_budget=100)).result, gr.BLOCK)
spend["recent"] = 0
# 4 ROAS ต่ำ -> auto pause
check("min ROAS -> PAUSE",
      gr.check_proposed_action(P(action="RAISE_BUDGET", new_daily_budget=200, target_roas=0.8)).result, gr.PAUSE)
# 5 learning phase
LEARN.update(in_learning=True, conversions=10)
check("learning phase block",
      gr.check_proposed_action(P(action="RAISE_BUDGET", ad_set_id=1, new_daily_budget=200)).result, gr.BLOCK)
LEARN.update(in_learning=False, conversions=999)
# 6 duplicate audience
DUP["exists"] = True
check("dup audience block",
      gr.check_proposed_action(P(action="CREATE_ADSET", audience_sig="abc")).result, gr.BLOCK)
DUP["exists"] = False
# 7 ผ่านหมด (live) -> ALLOW applied
v = gr.check_proposed_action(P(action="RAISE_BUDGET", ad_set_id=1, new_daily_budget=200))
check("valid raise ALLOW+applied", (v.result, v.applied), (gr.ALLOW, True))
# 8 dry-run -> ALLOW แต่ไม่ applied
CFG["dry_run"] = True
v = gr.check_proposed_action(P(action="RAISE_BUDGET", ad_set_id=1, new_daily_budget=200))
check("dry-run ALLOW not applied", (v.result, v.applied), (gr.ALLOW, False))

passed = sum(1 for *_ , ok in cases if ok)
print(f"\n{passed}/{len(cases)} guardrail tests passed")
sys.exit(0 if passed == len(cases) else 1)
