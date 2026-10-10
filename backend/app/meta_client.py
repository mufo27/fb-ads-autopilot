"""Meta Graph API client — validate key + sync insights + สร้าง/ปรับ ad
อ้างอิง quirks ที่รู้ไว้: time_range ต้อง --data-urlencode, geo TH, age 20-65
"""
import json
import httpx
from .config import get_settings

GRAPH = "https://graph.facebook.com/v21.0"


def _tok():
    return get_settings().meta_token()


async def validate_connection() -> dict:
    """เช็กว่า key ใช้ได้จริง — เรียก /me และ /me/adaccounts"""
    s = get_settings()
    out = {"ok": False, "checks": {}, "detail": None}
    if not s.meta_token():
        out["detail"] = "ยังไม่ได้ใส่ META token"
        return out
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.get(f"{GRAPH}/me", params={"access_token": _tok(), "fields": "id,name"})
            out["checks"]["token"] = r.status_code == 200
            me = r.json()
            # ad accounts
            r2 = await client.get(f"{GRAPH}/me/adaccounts", params={"access_token": _tok(), "fields": "account_id,name,currency"})
            accounts = r2.json().get("data", []) if r2.status_code == 200 else []
            acct_ids = [a.get("account_id") for a in accounts]
            out["checks"]["ad_account"] = s.META_AD_ACCOUNT_ID in acct_ids if s.META_AD_ACCOUNT_ID else bool(acct_ids)
            out["ok"] = out["checks"]["token"] and out["checks"]["ad_account"]
            out["detail"] = {"me": me, "accounts": accounts[:10]}
        except Exception as e:  # noqa
            out["detail"] = str(e)
    return out


async def get_campaign_insights(since: str, until: str) -> list:
    """ดึง insight ของ ad sets — time_range ต้องเป็น JSON (bracket notation พัง)"""
    s = get_settings()
    tr = json.dumps({"since": since, "until": until})
    params = {
        "access_token": _tok(),
        "fields": "account_id,name,daily_budget,spend,impressions,clicks,actions",
        "time_range": tr,
        "limit": 200,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{GRAPH}/{s.META_AD_ACCOUNT_ID}/adsets", params=params)
        r.raise_for_status()
        return r.json().get("data", [])


async def pause_adset(adset_id: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{GRAPH}/{adset_id}",
            data={"status": "PAUSED", "access_token": _tok()},
        )
        return r.json()


async def bulk_pause(adset_ids: list[str]) -> list[dict]:
    """หยุด ad sets หลายตัวบน Meta (best-effort ต่อตัว)"""
    out = []
    for aid in adset_ids:
        try:
            out.append({"id": aid, "result": await pause_adset(aid)})
        except Exception as e:  # noqa
            out.append({"id": aid, "error": str(e)})
    return out


async def update_adset_budget(adset_id: str, daily_budget_cents: int) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{GRAPH}/{adset_id}",
            data={"daily_budget": str(daily_budget_cents), "access_token": _tok()},
        )
        return r.json()
