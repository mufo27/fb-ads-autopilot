"""
sync.py — ดึง insight จาก Meta เข้า DB (เพื่อให้ velocity/hard-cap/ROAS ทำงานบนข้อมูลจริง)
และ emergency pause บน Meta จริงเมื่อเปิด kill switch

แยก pure-parse อออกมา (parse_insight) เพื่อทดสอบได้โดยไม่ต้องเรียก API
"""
from datetime import datetime, timedelta, timezone

from . import db, meta_client
from .config import get_settings


def parse_insight(row: dict) -> dict:
    """แปลงแถว insight ของ Meta adset ให้เป็น metric ที่ระบบใช้ (heuristic, ป้องกันค่าหาย)"""
    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    spend = _f(row.get("spend"))
    impressions = int(_f(row.get("impressions")))
    clicks = int(_f(row.get("clicks")))
    # daily_budget กลับมาเป็น "cents" (string) -> แปลงเป็นบาท
    daily_budget = _f(row.get("daily_budget")) / 100.0 if row.get("daily_budget") not in (None, "") else 0.0

    conversions, revenue = 0, 0.0
    for a in (row.get("actions") or []):
        at = (a.get("action_type") or "").lower()
        val = _f(a.get("value"))
        if at in ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase", "add_to_cart"):
            conversions += int(val)
    for a in (row.get("action_values") or []):
        at = (a.get("action_type") or "").lower()
        if "purchase" in at:
            revenue += _f(a.get("value"))
    return {
        "meta_adset_id": row.get("id"),
        "name": row.get("name") or "(no name)",
        "spend": round(spend, 2),
        "impressions": impressions,
        "clicks": clicks,
        "daily_budget": round(daily_budget, 2),
        "conversions": conversions,
        "revenue": round(revenue, 2),
    }


def _upsert_adset(m: dict, learning_min: int) -> int:
    """insert/update ad_set ตาม meta_adset_id แล้วคืน ad_set id (0 = ข้าม)"""
    if not m["meta_adset_id"]:
        return 0
    existing = db.query("SELECT id,spend FROM ad_sets WHERE meta_adset_id=%s", (m["meta_adset_id"],))
    if existing:
        sid = int(existing[0]["id"])
        old_spend = float(existing[0]["spend"] or 0)
        db.execute(
            """UPDATE ad_sets SET name=%s, spend=%s, conversions=%s, revenue=%s,
                   daily_budget=COALESCE(NULLIF(%s,0), daily_budget), in_learning=%s, updated_at=now()
               WHERE id=%s""",
            (m["name"], m["spend"], m["conversions"], m["revenue"], m["daily_budget"],
             m["conversions"] < learning_min, sid),
        )
        delta = round(m["spend"] - old_spend, 2)
        if delta > 0:
            db.execute("INSERT INTO spend_ledger(ad_set_id,spent) VALUES (%s,%s)", (sid, delta))
        return sid
    db.execute(
        """INSERT INTO ad_sets(meta_adset_id,name,spend,conversions,revenue,daily_budget,in_learning,status,audience_sig)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'ACTIVE',md5(%s))""",
        (m["meta_adset_id"], m["name"], m["spend"], m["conversions"], m["revenue"],
         m["daily_budget"], m["conversions"] < learning_min, m["meta_adset_id"]),
    )
    sid = db.query("SELECT id FROM ad_sets WHERE meta_adset_id=%s", (m["meta_adset_id"],))
    sid_id = int(sid[0]["id"]) if sid else 0
    if sid_id and m["spend"] > 0:
        db.execute("INSERT INTO spend_ledger(ad_set_id,spent) VALUES (%s,%s)", (sid_id, m["spend"]))
    return sid_id


async def pull_insights(since: str | None = None, until: str | None = None) -> dict:
    """ดึง insight 3 ย้อนหลังเข้า DB; ข้ามถ้ายังไม่มี token (fail-safe)"""
    s = get_settings()
    if not s.meta_token():
        return {"ok": False, "skipped": "ยังไม่ได้ใส่ Meta token"}
    today = datetime.now(timezone.utc).date()
    since = since or today.isoformat()
    until = until or today.isoformat()
    from .guardrails import _cfg
    learning_min = _cfg().learning_min_conv
    try:
        rows = await meta_client.get_campaign_insights(since, until)
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)}
    updated = 0
    for row in rows:
        if _upsert_adset(parse_insight(row), learning_min):
            updated += 1
    return {"ok": True, "synced": updated, "since": since, "until": until}


async def emergency_pause_all() -> dict:
    """S5: หยุด ad sets ที่ ACTIVE (และมี meta id) บน Meta จริง + อัปเดต DB"""
    rows = db.query(
        "SELECT id, meta_adset_id FROM ad_sets WHERE status='ACTIVE' AND meta_adset_id IS NOT NULL"
    )
    ids = [r["meta_adset_id"] for r in rows]
    results = await meta_client.bulk_pause(ids) if ids else []
    for r in rows:
        db.execute("UPDATE ad_sets SET status='PAUSED', updated_at=now() WHERE id=%s", (r["id"],))
    ok = sum(1 for x in results if "error" not in x)
    return {"attempted": len(ids), "paused_meta": ok, "local_paused": len(rows)}
