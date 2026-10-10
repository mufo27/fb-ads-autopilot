"""
AI decision engine — ให้ AI วิเคราะห์ insight แล้ว 'เสนอ' รายการกระทำ
ทุกข้อเสนอก่อนทำจริง ต้องส่งผ่าน guardrails.check_proposed_action() เสมอ
รองรับ openai / anthropic / ollama + มี heuristic fallback เวลาไม่มี key
"""
import json
import httpx
from . import db
from . import meta_client
from . import security
from .config import get_settings
from .guardrails import ProposedAction, check_proposed_action, PAUSE, ALLOW, _cfg

SYSTEM_PROMPT = """คุณเป็นผู้จัดการ Facebook Ads สำหรับ Shopee Affiliate (เพจป้ายยา)
กติกาตายตัว: ห้ามเสนอเกินงบที่ระบบให้, ห้ามแตะ ad set ที่ยัง Learning,
ห้าม audience/creative ทับซ้อน, ROAS ต่ำกว่าเกณฑ์ให้เสนอ PAUSE ไม่ใช่เพิ่มงบ,
หมุนหลายสินค้า (product rotation) ห้ามทุ่มตัวเดียว
ตอบเป็น JSON: {"actions":[{"action":"RAISE_BUDGET|LOWER_BUDGET|PAUSE|CREATE_ADSET",
"ad_set_id":int|null,"campaign_id":int|null,"new_daily_budget":float|null,
"reason":str,"product":str|null}]}"""


def _rows_to_context() -> str:
    adsets = db.query("""SELECT id,campaign_id,name,product,daily_budget,spend,conversions,revenue,in_learning
                         FROM ad_sets ORDER BY spend DESC LIMIT 50""")
    for a in adsets:
        a["roas"] = round(float(a["revenue"]) / float(a["spend"]), 2) if float(a["spend"]) else 0
    return json.dumps(adsets, ensure_ascii=False, default=str)


async def propose_actions() -> list:
    """เรียก AI ให้เสนอ action; fallback = heuristic ถ้าไม่มี key/เรียกพัง"""
    s = get_settings()
    context = _rows_to_context()
    if s.AI_PROVIDER in ("openai", "ollama") and (s.AI_API_KEY or s.AI_PROVIDER == "ollama"):
        try:
            return await _ask_openai(context)
        except Exception:  # noqa
            pass
    return _heuristic(context)


async def _ask_openai(context: str) -> list:
    s = get_settings()
    url = s.AI_BASE_URL.rstrip("/") + "/chat/completions"
    body = {
        "model": s.AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"ข้อมูล ad sets ตอนนี้:\n{context}\nงบรายวันเหลือเท่าไหร่ก็อย่าเกิน เสนอรายการกระทำ"},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if s.AI_API_KEY:
        headers["Authorization"] = f"Bearer {s.AI_API_KEY}"
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
    return json.loads(content).get("actions", [])


def _heuristic(context: str) -> list:
    """กฎง่ายๆ ถ้า AI unavailable: ชนะ→เพิ่มงบ, ตก→pause, Learning→ห้ามแตะ"""
    from .guardrails import _cfg
    c = _cfg()
    out = []
    for a in json.loads(context):
        roas = a.get("roas", 0)
        if a.get("in_learning"):
            continue
        if roas >= c.min_roas:
            out.append({"action": "RAISE_BUDGET", "ad_set_id": a["id"], "campaign_id": a["campaign_id"],
                        "new_daily_budget": round(float(a["daily_budget"]) * 1.2, 0),
                        "reason": f"ROAS {roas} ดี → เพิ่มงบ 20%"})
        elif roas < c.min_roas and float(a["spend"]) > 0:
            out.append({"action": "PAUSE", "ad_set_id": a["id"], "campaign_id": a["campaign_id"],
                        "reason": f"ROAS {roas} ต่ำกว่าเกณฑ์ → pause"})
    return out


async def run_autopilot_cycle() -> list:
    """1 รอบ autopilot: AI เสนอ → guardrail กรอง → (ถ้าไม่ใช่ dry-run) ยิง Meta จริง"""
    proposals = await propose_actions()
    dry = _cfg().dry_run
    results = []
    for p in proposals:
        action = ProposedAction(
            action=p.get("action", "UNKNOWN"),
            ad_set_id=p.get("ad_set_id"),
            campaign_id=p.get("campaign_id"),
            new_daily_budget=p.get("new_daily_budget"),
        )
        if action.action == "RAISE_BUDGET" and action.ad_set_id:
            row = db.query("SELECT revenue,spend FROM ad_sets WHERE id=%s", (action.ad_set_id,))
            if row and float(row[0]["spend"]):
                action.target_roas = round(float(row[0]["revenue"]) / float(row[0]["spend"]), 3)
        verdict = check_proposed_action(action)  # S3: บังคับกรองทุกครั้ง
        meta_pushed = False
        if verdict.applied and verdict.result == ALLOW and action.ad_set_id and not security.is_killed():
            meta_pushed = await _apply(action, dry)
        results.append({"action": action.action, "verdict": verdict.result,
                        "reason": verdict.reason, "rule": verdict.rule,
                        "applied": verdict.applied, "meta_pushed": meta_pushed})
    return results


async def _apply(action: ProposedAction, dry: bool) -> bool:
    """อัปเดต state ใน DB เสมอ; ยิง Meta จริงเฉพาะตอน live (ไม่ dry-run) และมี meta id"""
    meta_id = None
    row = db.query("SELECT meta_adset_id FROM ad_sets WHERE id=%s", (action.ad_set_id,))
    if row:
        meta_id = row[0].get("meta_adset_id")
    pushed = False
    if action.action == "PAUSE":
        db.execute("UPDATE ad_sets SET status='PAUSED', updated_at=now() WHERE id=%s", (action.ad_set_id,))
        if not dry and meta_id:
            await meta_client.pause_adset(meta_id)
            pushed = True
    elif action.action in ("RAISE_BUDGET", "LOWER_BUDGET") and action.new_daily_budget is not None:
        db.execute("UPDATE ad_sets SET daily_budget=%s, updated_at=now() WHERE id=%s",
                   (action.new_daily_budget, action.ad_set_id))
        if not dry and meta_id:
            await meta_client.update_adset_budget(meta_id, int(action.new_daily_budget * 100))
            pushed = True
    return pushed
