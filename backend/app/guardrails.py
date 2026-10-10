"""
Guardrail engine — 4 ชั้นเบรกที่ AI 'ข้ามไม่ได้'
ทุกการตัดสินใจของ AI ต้องผ่าน check_proposed_action() ก่อนเสมอ
"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
from . import db
from . import security
from .config import get_settings

# verdict codes
ALLOW = "ALLOW"
BLOCK = "BLOCK"
PAUSE = "PAUSE"


@dataclass
class ProposedAction:
    action: str                 # RAISE_BUDGET / LOWER_BUDGET / LAUNCH / CREATE_ADSET / PAUSE ...
    ad_set_id: Optional[int] = None
    campaign_id: Optional[int] = None
    new_daily_budget: Optional[float] = None        # ถ้าเป็นการปรับงบ
    target_roas: Optional[float] = None
    audience_sig: Optional[str] = None
    content_sig: Optional[str] = None


@dataclass
class Verdict:
    result: str
    reason: str
    rule: str
    applied: bool = False


def _cfg():
    """อ่าน guardrail config จาก DB (fallback = env)"""
    s = get_settings()
    rows = db.query("SELECT * FROM guardrail_config ORDER BY id DESC LIMIT 1")
    if not rows:
        return s
    r = rows[0]
    return type("C", (), {
        "daily_hard_cap": float(r["daily_hard_cap"]),
        "per_campaign_cap": float(r["per_campaign_cap"]),
        "velocity_window_min": int(r["velocity_window_min"]),
        "velocity_max_pct": int(r["velocity_max_pct"]),
        "min_roas": float(r["min_roas"]),
        "learning_min_conv": int(r["learning_min_conv"]),
        "dry_run": bool(r["dry_run"]),
    })()


def _spend_today() -> float:
    day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.query("SELECT COALESCE(SUM(spent),0) AS s FROM spend_ledger WHERE occurred_at >= %s", (day_start,))
    return float(rows[0]["s"] or 0)


def _spend_recent(minutes: int) -> float:
    since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = db.query("SELECT COALESCE(SUM(spent),0) AS s FROM spend_ledger WHERE occurred_at >= %s", (since,))
    return float(rows[0]["s"] or 0)


def check_proposed_action(a: ProposedAction) -> Verdict:
    """ตัวกรองกลาง: คืน Verdict ว่า ALLOW/BLOCK/PAUSE + เหตุผลที่ผูกกับกฎข้อไหน"""
    c = _cfg()

    # --- S5: Kill switch — ถ้าคนสั่งปิด ห้าม AI สั่งใช้เงิน (แต่ยัง 'หยุด' ได้) ---
    if security.is_killed() and a.action != "PAUSE":
        return _log(a, Verdict(BLOCK, "ระบบถูกสั่งหยุด (KILL SWITCH ON) — AI ห้ามใช้เงินทุกกรณี", "KILL_SWITCH"))

    # --- ชั้น 1: กรอบเงิน ---------------------------------------------------
    if a.new_daily_budget is not None:
        if a.new_daily_budget > c.per_campaign_cap:
            return _log(a, Verdict(BLOCK, f"งบ {a.new_daily_budget:.0f} เกินเพดานต่อกามเปญ {c.per_campaign_cap:.0f}", "PER_CAMPAIGN_CAP"))

    # hard cap รายวัน: ถ้างบใหม่/ปัจจุบันจะทำให้ยอดวันนี้พุ่งเกินเพดาน = บล็อก
    projected_today = _spend_today()
    if a.action in ("RAISE_BUDGET", "LAUNCH") and a.new_daily_budget:
        if projected_today + a.new_daily_budget > c.daily_hard_cap:
            return _log(a, Verdict(BLOCK, f"จะเกินงบรายวัน hard cap {c.daily_hard_cap:.0f} (วันนี้ใช้แล้ว {projected_today:.0f})", "DAILY_HARD_CAP"))

    # velocity: ห้ามเผาเกิน velocity_max_pct% ของงบรายวันใน window (บล็อกเฉพาะ action ที่ 'เพิ่ม' การใช้เงิน)
    window_spend = _spend_recent(c.velocity_window_min)
    velocity_limit = c.daily_hard_cap * c.velocity_max_pct / 100
    if a.action in ("RAISE_BUDGET", "LAUNCH", "CREATE_ADSET") and window_spend >= velocity_limit:
        return _log(a, Verdict(BLOCK, f"ใช้เงิน {window_spend:.0f} ใน {c.velocity_window_min} นาที = เกิน velocity limit {velocity_limit:.0f}", "SPEND_VELOCITY"))

    # --- ชั้น 1b: auto-pause เมื่อ ROAS ตก ---------------------------------
    if a.action == "RAISE_BUDGET" and a.target_roas is not None and a.target_roas < c.min_roas:
        return _log(a, Verdict(PAUSE, f"ROAS {a.target_roas:.2f} < เกณฑ์ {c.min_roas:.2f} → หยุด ad set นี้แทนการเพิ่มงบ", "MIN_ROAS"))

    # --- ชั้น 2: วินัยแอดฯ --------------------------------------------------
    if a.action == "RAISE_BUDGET" and a.ad_set_id:
        row = db.query("SELECT in_learning, conversions FROM ad_sets WHERE id=%s", (a.ad_set_id,))
        if row and row[0]["in_learning"] and int(row[0]["conversions"]) < c.learning_min_conv:
            return _log(a, Verdict(BLOCK, f"ad set ยังอยู่ใน Learning Phase (conv {row[0]['conversions']} < {c.learning_min_conv}) ห้ามแตะงบ", "LEARNING_PHASE"))

    if a.action == "CREATE_ADSET" and a.audience_sig:
        dup = db.query("SELECT id FROM ad_sets WHERE audience_sig=%s AND status='ACTIVE'", (a.audience_sig,))
        if dup:
            return _log(a, Verdict(BLOCK, "audience ทับซ้อนกับ ad set ที่ Active อยู่ (กันประมูลชนกัน)", "NO_DUPLICATE_AUDIENCE"))

    if a.action == "CREATE_ADSET" and a.content_sig:
        dup = db.query("SELECT id FROM creatives WHERE content_sig=%s", (a.content_sig,))
        if dup:
            return _log(a, Verdict(BLOCK, "creative ซ้ำกับที่มีอยู่แล้ว (ต้อง rotate/ทำใหม่)", "NO_DUPLICATE_CREATIVE"))

    # --- ผ่านทุกด่าน --------------------------------------------------------
    # PAUSE action เสมอได้รับอนุญาต (หยุดอัตโนมัติทำได้) + ไม่ติด dry-run
    applied = True
    if c.dry_run and a.action in ("RAISE_BUDGET", "LAUNCH", "CREATE_ADSET", "LOWER_BUDGET"):
        v = Verdict(ALLOW, "[DRY-RUN] ตัดสินใจผ่านทุก guardrail แต่ยังไม่ยิงจริง", "DRY_RUN", applied=False)
    else:
        v = Verdict(ALLOW, "ผ่านทุก guardrail", "NONE", applied=applied)
    return _log(a, v)


def update_config(**kwargs) -> int:
    """ปรับ guardrail ผ่าน API/dashboard (daily_hard_cap ฯลฯ) — log ทุกครั้ง"""
    allowed = {"daily_hard_cap", "per_campaign_cap", "velocity_window_min",
               "velocity_max_pct", "min_roas", "learning_min_conv", "dry_run"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return 0
    # S6: daily_hard_cap ห้ามเกินเพดานระบบ (ต่อให้มี admin token ก็ขยายมั่วไม่ได้)
    if "daily_hard_cap" in fields:
        fields["daily_hard_cap"] = security.clamp_daily_cap(fields["daily_hard_cap"])
    sets = ", ".join(f"{k}=%s" for k in fields)
    vals = list(fields.values())
    db.execute(f"UPDATE guardrail_config SET {sets}, updated_at=now() WHERE id=(SELECT MAX(id) FROM guardrail_config)", vals)
    get_settings().LOG_LEVEL
    _audit("UPDATE_GUARDRAIL", "guardrail_config", str(fields), "ALLOW", "ผู้ใช้ปรับกรอบเหล็กเอง", "USER", True)
    return len(fields)


def get_config() -> dict:
    c = _cfg()
    return {
        "daily_hard_cap": c.daily_hard_cap,
        "per_campaign_cap": c.per_campaign_cap,
        "velocity_window_min": c.velocity_window_min,
        "velocity_max_pct": c.velocity_max_pct,
        "min_roas": c.min_roas,
        "learning_min_conv": c.learning_min_conv,
        "dry_run": c.dry_run,
        "spend_today": _spend_today(),
        "remaining_today": max(0.0, c.daily_hard_cap - _spend_today()),
    }


def _log(a: ProposedAction, v: Verdict) -> Verdict:
    _audit(a.action, f"ad_set={a.ad_set_id} campaign={a.campaign_id}",
           str(a.new_daily_budget), v.result, v.reason, v.rule, v.applied)
    return v


def _audit(action, target, proposed, verdict, reason, rule, applied):
    db.execute(
        """INSERT INTO ai_decisions
           (action,target,proposed_value,verdict,reason,guardrail_rule,applied)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (action, target, proposed, verdict, reason, rule, applied),
    )
