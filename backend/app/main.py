"""FB Ads Autopilot — FastAPI entrypoint"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import db, guardrails, meta_client, ai_engine, credentials, security, ratelimit, sync, auth
from .config import get_settings

s = get_settings()
logging.basicConfig(level=s.LOG_LEVEL)
log = logging.getLogger("autopilot")


def _ident(request: Request, token: str | None) -> str:
    ip = request.client.host if request.client else "?"
    return f"{ip}|{(token or '')[:12]}"


def rl(limit: int, window_s: int, scope: str):
    """dependency: จำกัดจำนวน call ต่อ (ip+token) ในหน้าต่างเวลา — กัน brute-force/spam"""
    def dep(request: Request, x_admin_token: Optional[str] = Header(None)):
        ok, retry = ratelimit.allow(f"{scope}:{_ident(request, x_admin_token)}", limit, window_s)
        if not ok:
            raise HTTPException(429, f"เรียกถี่เกินไป ลองใหม่ใน {retry}s",
                                headers={"Retry-After": str(retry)})
        return True
    return dep


def require_admin(request: Request, x_admin_token: Optional[str] = Header(None),
                  authorization: Optional[str] = Header(None),
                  session: Optional[str] = Cookie(None)):
    """gate: ยอมรับ (1) session cookie จาก login หรือ (2) ADMIN_TOKEN (owner/API) — ไม่งั้น 401 fail-closed"""
    token = x_admin_token or (authorization[7:] if authorization and authorization.startswith("Bearer ") else None)
    # กันเดาสุ่ม: สูงสุด 300 ครั้ง/นาที ต่อ ip+token
    ok, retry = ratelimit.allow(f"auth:{_ident(request, token)}", 300, 60)
    if not ok:
        raise HTTPException(429, f"พยายามบ่อยเกินไป ลองใหม่ใน {retry}s", headers={"Retry-After": str(retry)})
    # 1) session cookie
    user = auth.read_session(session)
    if user:
        return user
    # 2) admin token (owner / สคริปต์)
    if security.auth_enabled() and security.verify_admin_token(token or ""):
        return {"role": "owner", "email": "owner"}
    raise HTTPException(401, "ต้องเข้าสู่ระบบ")


def sync_guardrails_from_env():
    guardrails.update_config(
        daily_hard_cap=s.GUARD_DAILY_HARD_CAP,
        per_campaign_cap=s.GUARD_PER_CAMPAIGN_CAP,
        velocity_window_min=s.GUARD_VELOCITY_WINDOW_MIN,
        velocity_max_pct=s.GUARD_VELOCITY_MAX_PCT,
        min_roas=s.GUARD_MIN_ROAS,
        learning_min_conv=s.GUARD_LEARNING_MIN_CONV,
        dry_run=s.GUARD_DRY_RUN,
    )


async def autopilot_loop():
    while True:
        try:
            if security.is_killed():
                log.warning("autopilot skip: KILL SWITCH ON")
            else:
                sy = await sync.pull_insights()          # 1) ดึงข้อมูลจริงเข้า DB
                log.info("sync: %s", sy)
                res = await ai_engine.run_autopilot_cycle()  # 2) AI คิด → guardrail กรอง → ยิง
                log.info("autopilot cycle: %d actions", len(res))
        except Exception as e:  # noqa
            log.exception("autopilot cycle failed: %s", security.redact(str(e)))
        await asyncio.sleep(30 * 60)  # ทุก 30 นาที


def _load_kill_state():
    try:
        db.execute("CREATE TABLE IF NOT EXISTS sys_flags(name TEXT PRIMARY KEY, value TEXT)")
        rows = db.query("SELECT value FROM sys_flags WHERE name='kill_switch'")
        security.set_killed(bool(rows and rows[0]["value"] == "1"))
    except Exception:  # noqa
        pass


def _save_kill_state(flag: bool):
    db.execute("""INSERT INTO sys_flags(name,value) VALUES('kill_switch',%s)
                  ON CONFLICT(name) DO UPDATE SET value=excluded.value""", ("1" if flag else "0",))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        credentials.ensure_table()
        auth.ensure_users_table()
        credentials.apply_to_settings()   # ดึง key ที่ผู้ใช้เคยใส่ (จาก DB) ขึ้นมาใช้ก่อน env
        _load_kill_state()
        sync_guardrails_from_env()
    except Exception as e:  # noqa
        log.warning("db not ready yet: %s", e)
    if not security.auth_enabled():
        log.warning("⚠️ ADMIN_TOKEN ไม่ได้ตั้งค่า — ทุก endpoint (ยกเว้น /api/health) จะถูกปฏิเสธ 403 (fail-closed)")
    if not (s.SECURITY_KEY or "").strip():
        log.warning("⚠️ SECURITY_KEY ไม่ได้ตั้งค่า — จะบันทึก secret ไม่ได้ (fail-closed)")
    task = asyncio.create_task(autopilot_loop())
    yield
    task.cancel()


app = FastAPI(title="FB Ads Autopilot", lifespan=lifespan)
# S: CORS ล็อกเฉพาะ origin frontend (ห้าม *) — กันเว็บอื่นเรียก API จากเบราว์เซอร์
_origins = [o.strip() for o in s.FRONTEND_ORIGIN.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_methods=["*"],
    allow_headers=["*"], allow_credentials=True,
)


# ---- Health & connect -------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "dry_run": guardrails.get_config()["dry_run"], "keys": s.keys_provided()}


# ---- Auth (login / register / OAuth) -----------------------------------------
def _set_session(resp: Response, user: dict):
    resp.set_cookie(auth.COOKIE, auth.create_session(user), httponly=True, samesite="lax",
                    secure=False, max_age=auth.SESSION_TTL, path="/")


def _public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u.get("email"), "name": u.get("name"),
            "role": u.get("role", "user"), "provider": u.get("provider", "password")}


@app.post("/api/auth/register")
def auth_register(body: dict, resp: Response):
    email = (body.get("email") or "").strip()
    name = (body.get("name") or "").strip()
    pw = body.get("password") or ""
    if not email or "@" not in email:
        raise HTTPException(400, "อีเมลไม่ถูกต้อง")
    if len(pw) < 8:
        raise HTTPException(400, "รหัสผ่านอย่างน้อย 8 ตัวอักษร")
    try:
        u = auth.register_password(email, name or email.split("@")[0], pw)
    except ValueError as e:
        raise HTTPException(409, str(e))
    _set_session(resp, u)
    return {"ok": True, "user": _public_user(u)}


@app.post("/api/auth/login")
def auth_login(body: dict, resp: Response):
    u = auth.login_password((body.get("email") or "").strip(), body.get("password") or "")
    if not u:
        raise HTTPException(401, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    _set_session(resp, u)
    return {"ok": True, "user": _public_user(u)}


@app.get("/api/auth/me")
def auth_me(session: Optional[str] = Cookie(None)):
    p = auth.read_session(session)
    if not p:
        raise HTTPException(401, "ไม่ได้เข้าสู่ระบบ")
    u = auth.get_by_id(p["uid"]) or {"id": p["uid"], "email": p.get("email"), "name": p.get("name"), "role": p.get("role", "user")}
    return {"user": _public_user(u)}


@app.post("/api/auth/profile")
def auth_update_profile(body: dict, session: Optional[str] = Cookie(None)):
    p = auth.read_session(session)
    if not p:
        raise HTTPException(401, "ไม่ได้เข้าสู่ระบบ")
    try:
        auth.update_name(p["uid"], body.get("name", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "user": _public_user(auth.get_by_id(p["uid"]))}


@app.post("/api/auth/change-password")
def auth_change_pw(body: dict, session: Optional[str] = Cookie(None),
                   _: bool = Depends(rl(5, 60, "chpw"))):
    p = auth.read_session(session)
    if not p:
        raise HTTPException(401, "ไม่ได้เข้าสู่ระบบ")
    try:
        auth.change_password(p["uid"], body.get("old_password", ""), body.get("new_password", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(resp: Response):
    resp.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/oauth-providers")
def auth_providers():
    return {"google": auth.oauth_configured("google"), "facebook": auth.oauth_configured("facebook")}


@app.get("/api/auth/{provider}/start")
def auth_start(provider: str):
    if provider not in ("google", "facebook"):
        raise HTTPException(404, "unknown provider")
    if not auth.oauth_configured(provider):
        raise HTTPException(400, f"ยังไม่ได้ตั้งค่า {provider} OAuth (ใส่ client id/secret ใน env)")
    state = auth.new_state()
    r = RedirectResponse(auth.authorize_url(provider, state))
    r.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600, path="/")
    return r


@app.get("/api/auth/{provider}/callback")
async def auth_callback(provider: str, code: str = "", state: str = "", oauth_state: Optional[str] = Cookie(None)):
    if provider not in ("google", "facebook") or not code:
        raise HTTPException(400, "คำขอ OAuth ไม่ถูกต้อง")
    if not state or state != oauth_state:
        raise HTTPException(400, "state ไม่ตรง (กัน CSRF)")
    try:
        prof = await (auth.exchange_google(code) if provider == "google" else auth.exchange_facebook(code))
        u = auth.upsert_oauth(provider, prof["pid"], prof.get("email"), prof.get("name"))
    except Exception as e:  # noqa
        raise HTTPException(502, f"OAuth ล้มเหลว: {e}")
    r = RedirectResponse(f"{s.FRONTEND_ORIGIN}?authed=1")
    _set_session(r, u)
    r.delete_cookie("oauth_state", path="/")
    return r


@app.post("/api/connect/validate")
async def validate(_: bool = Depends(require_admin), __: bool = Depends(rl(10, 60, "validate"))):
    """เช็กว่า Meta key ใช้ได้จริง + บอกว่าขาด key ไหน (rate-limit 10/นาที)"""
    return await meta_client.validate_connection()


# ---- User-supplied credentials (ใส่เองผ่านเว็บ, เข้ารหัสใน DB, mask) -------------
@app.get("/api/settings")
def get_settings_api(_: bool = Depends(require_admin)):
    """คืนค่าที่ mask แล้วเท่านั้น — ไม่มี token/key ลับหลุดออกมา (S4)"""
    return {"fields": credentials.status()}


@app.post("/api/settings")
def set_settings_api(body: dict, _: bool = Depends(require_admin),
                     __: bool = Depends(rl(30, 60, "set"))):
    """ผู้ใช้กรอก key/token เอง → เข้ารหัส secret ลง DB (S1) → validate"""
    try:
        n = credentials.save(body or {})
    except security.SecurityError as e:
        raise HTTPException(400, str(e))
    return {"saved": n, "fields": credentials.status()}


# ---- Sync insights จาก Meta → DB ---------------------------------------------
@app.post("/api/sync")
async def sync_now(_: bool = Depends(require_admin), __: bool = Depends(rl(6, 60, "sync"))):
    return await sync.pull_insights()


# ---- Kill switch (S5) --------------------------------------------------------
@app.post("/api/kill")
async def kill(on: bool, _: bool = Depends(require_admin),
               __: bool = Depends(rl(30, 60, "kill"))):
    """เปิด/ปิด kill switch — ถ้า ON จะสั่ง PAUSED ทุก ad set บน Meta จริง"""
    security.set_killed(on)
    try:
        _save_kill_state(on)
    except Exception:  # noqa
        pass
    paused = await sync.emergency_pause_all() if on else None
    guardrails._audit("KILL_SWITCH", "system", str(on), "ALLOW",
                      f"human สั่ง kill switch (paused on Meta: {paused})", "USER", True)
    return {"killed": security.is_killed(), "paused": paused}


# ---- Guardrails -------------------------------------------------------------
@app.get("/api/guardrails")
def get_guard(_: bool = Depends(require_admin)):
    return guardrails.get_config()


@app.post("/api/guardrails")
def set_guard(body: dict, _: bool = Depends(require_admin),
              __: bool = Depends(rl(20, 60, "setguard"))):
    n = guardrails.update_config(**body)   # S6: clamp daily cap ภายใน
    return {"updated": n, "config": guardrails.get_config()}


# ---- Decisions (audit log) --------------------------------------------------
@app.get("/api/decisions")
def decisions(limit: int = 50, _: bool = Depends(require_admin)):
    return db.query("SELECT * FROM ai_decisions ORDER BY ts DESC LIMIT %s", (limit,))


# ---- Dashboard overview -----------------------------------------------------
@app.get("/api/overview")
def overview(_: bool = Depends(require_admin)):
    cfg = guardrails.get_config()
    camp = db.query("SELECT COUNT(*) c FROM campaigns WHERE status='ACTIVE'")[0]["c"]
    adsets = db.query("SELECT id,name,product,daily_budget,spend,conversions,revenue,in_learning,status FROM ad_sets ORDER BY spend DESC LIMIT 20")
    for a in adsets:
        a["roas"] = round(float(a["revenue"]) / float(a["spend"]), 2) if float(a["spend"]) else 0
    return {
        "spend_today": cfg["spend_today"],
        "remaining_today": cfg["remaining_today"],
        "daily_hard_cap": cfg["daily_hard_cap"],
        "dry_run": cfg["dry_run"],
        "killed": security.is_killed(),
        "active_campaigns": camp,
        "ad_sets": adsets,
    }


# ---- AI control ------------------------------------------------------------
@app.post("/api/autopilot/run")
async def run_now(_: bool = Depends(require_admin), __: bool = Depends(rl(6, 60, "run"))):
    if security.is_killed():
        return {"cycle": [], "killed": True}
    return {"cycle": await ai_engine.run_autopilot_cycle()}


@app.post("/api/demo/seed")
def seed_demo(_: bool = Depends(require_admin), __: bool = Depends(rl(10, 60, "seed"))):
    """สร้างข้อมูลตัวอย่างเพื่อให้ dashboard ทำงานได้ตอน dev"""
    db.execute("INSERT INTO campaigns(name,product,status,daily_budget) VALUES (%s,%s,'ACTIVE',%s)",
               ("ป้ายยา-แกดเจ็ต", "powerbank", 300))
    cid = db.query("SELECT id FROM campaigns ORDER BY id DESC LIMIT 1")[0]["id"]
    rows = [
        ("AdSet-A ชนะ", "powerbank", 200, 180, 40, 540, False, "ACTIVE"),
        ("AdSet-B Learning", "usb-c", 150, 60, 10, 90, True, "ACTIVE"),
        ("AdSet-C ตก", "cable", 100, 95, 3, 60, False, "ACTIVE"),
    ]
    for name, prod, b, sp, conv, rev, learn, st in rows:
        db.execute("""INSERT INTO ad_sets(campaign_id,name,product,daily_budget,spend,conversions,revenue,in_learning,status,audience_sig)
                      VALUES (%s,%s,NULLIF(%s,''),%s,%s,%s,%s,%s,%s,md5(%s))""",
                   (cid, name, prod, b, sp, conv, rev, learn, st, prod))
        sid = db.query("SELECT id FROM ad_sets ORDER BY id DESC LIMIT 1")[0]["id"]
        db.execute("INSERT INTO spend_ledger(ad_set_id,spent) VALUES (%s,%s)", (sid, sp))
    return {"seeded": True}
