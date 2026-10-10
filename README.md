# FB Ads Autopilot

ระบบยิง Facebook Ads อัตโนมัติด้วย AI — จัดการหมุนสินค้า/ปรับงบ/หยุดแอดเอง
แต่ **ไม่มีทางใช้เงินเกิน "กรอบเหล็ก (Guardrails)"** ที่กำหนด
เชื่อม Meta + AI ง่ายแบบ "ใส่แค่ key"

> สถานะ: skeleton พร้อมรัน (`docker compose up`) — AI ตัดสินใจ + กรองผ่าน guardrail ทำงานได้จริง
> ส่วน sync insight จาก Meta จริงเชื่อม endpoint ไว้แล้ว (`meta_client.py`)

## รันใน 3 ขั้นตอน

```bash
cd fb-ads-autopilot
cp .env.example .env          # 1) ตั้งค่าเบื้องต้น (ไม่ต้องมี key/Meta ก็รันได้)
docker compose up --build     # 2) รันทั้งระบบ
# 3) เปิด http://localhost:3000 → ไปที่การ์ด "🔑 Connect Keys" กรอก token เอง
```

## 🔑 Key/Token = User กรอกเองบนหน้าเว็บ (ไม่ hardcode ในโค้ด/.env)
- ใส่ที่การ์ด **Connect Keys** แล้วกด "บันทึก & เชื่อมต่อ" → ระบบตรวจ Meta ให้ทันที
- เก็บในตาราง DB `app_credentials` ตอนบูตจะดึงค่านี้ขึ้นมาก่อนค่าใน env
- **ค่าลับถูก mask** ใน API/UI (โชว์แค่ 4 ตัวท้าย เช่น `••••9f3d`) ไม่มี tokenหลุดกลับไป
- ช่องที่ขึ้น `••••` = มีค่าอยู่แล้ว เว้นว่างไว้ = ใช้ค่าเดิม ไม่ต้องพิมพ์ซ้ำ

| ช่อง | ใส่ในเว็บ | ความลับ |
|---|---|---|
| Meta App ID / Ad Account ID / Page ID | Connect Keys | ไม่ใช่ (โชว์เต็ม) |
| Meta App Secret / Page Token / Marketing Token | Connect Keys | ใช่ (mask) |
| AI Provider / Model / API Key | Connect Keys | key = mask |

`.env` ใช้เก็บเฉพาะค่าตั้งต้นที่ไม่ใช่ความลับ (guardrail caps, AI_PROVIDER) หรือจะใส่ env ไว้ก็ได้ถ้าถนัด — ค่าจากเว็บจะทับ env

## Guardrails (กฎเหล็ก 4 ชั้น) — ค่าเริ่มต้นตั้งที่ `.env` / แก้ในหน้าเว็บได้
1. **กรอบเงิน (ห้ามข้าม)**
   - `GUARD_DAILY_HARD_CAP` — เพดานงบรายวันทั้งระบบ (AI เพิ่มเองไม่ได้)
   - `GUARD_PER_CAMPAIGN_CAP` — เพดานต่อกามเปญ
   - `GUARD_VELOCITY_*` — ห้ามเผาเงินเร็วเกิน X% ของงบภายใน Y นาที
   - `GUARD_MIN_ROAS` — ROAS ต่ำกว่านี้ → **auto-pause** (หยุดอัตโนมัติได้ แต่จะไม่ "เพิ่มงบ")
2. **วินัยแอด** — ห้ามแตะ ad set ที่ยัง Learning, ห้าม audience/creative ทับซ้อน (กันประมูลชน)
3. **Dry-run** (`GUARD_DRY_RUN=true`) — AI คิด+log ครบแต่ยังไม่ยิงเงินจริง สลับเป็น LIVE ได้จากเว็บ
4. **Audit log** — ทุกการตัดสินใจเก็บในตาราง `ai_decisions` ดูย้อนได้ในแดชบอร์ด

> ⚠️ เมื่อปิด dry-run = AI ยิงเงินจริงอัตโนมัติจนถึงเพดาน ตรวจ `GUARD_DAILY_HARD_CAP` ให้เหมาะก่อนเสมอ

## โครงสร้าง
```
backend/   FastAPI: guardrails engine, meta_client, ai_engine, REST API
frontend/  Next.js: แดชบอร์ดดาร์ก (ส้ม-น้ำเงิน)
db/init.sql  schema: campaigns, ad_sets, creatives, spend_ledger, ai_decisions, guardrail_config
```

## API ที่สำคัญ
- `GET /api/settings` (ค่า mask) · `POST /api/settings` (ผู้ใช้กรอก key/token เอง → เข้ารหัสลง DB)
- `GET /api/overview` · `GET /api/guardrails` · `POST /api/guardrails` (ปรับกรอบ)
- `POST /api/connect/validate` (เช็ก Meta) · `POST /api/sync` (ดึง insight เข้า DB)
- `POST /api/autopilot/run` (AI ตัดสินใจ 1 รอบ) · `POST /api/kill?on=true` (หยุด+pause Meta จริง)
- `GET /api/decisions` (audit log) · `POST /api/demo/seed` (ข้อมูลตัวอย่างตอน dev)
- ทุก endpoint (ยกเว้น health) ต้องส่ง header `X-Admin-Token` และมี rate-limit → เกินคืน `429`

## 🔒 หลักความปลอดภัย (Security Invariants — ยึดเป็นแกน, fail-closed)

> ระบบนี้ถือ Meta token + ใบอนุญาตใช้เงิน จึงออกแบบให้ "ถ้าไม่ปลอดภัย = ปฏิเสธการทำงาน" ไม่ใช่ปล่อยผ่าน

| # | หลัก | การป้องกัน (prevent) | ตรวจพบ (detect) / บันทึก (log) |
|---|---|---|---|
| S1 | ความลับต้องเข้ารหัสก่อนลง disk/DB | Fernet/AES encrypt ค่า secret ใน `app_credentials`; ไม่มี `SECURITY_KEY` = บันทึกไม่ได้ (throw) | key เปลี่ยน → ถอดไม่สำเร็จ = ถือว่ายังไม่ได้ใส่ ไม่ใช้ค่ามั่ว |
| S2 | ทุก API ที่ใช้เงิน/อ่าน-เขียน key ต้อง auth | `X-Admin-Token` ตรวจ constant-time; ไม่มี `ADMIN_TOKEN` = ทุก endpoint (ยกเว้น health) ตอบ 403 | 403 ทุกครั้งที่ token ผิด |
| S3 | AI แตะเงินไม่ได้โดยตรง | ข้อเสนอสั้นๆ **ต้องผ่าน `guardrails.check_proposed_action()` เสมอ** (บังคับในโค้ด) | log ทุก ALLOW/BLOCK/PAUSE + กฎที่ใช้ |
| S4 | ห้ามค่าลับหลุดใน response/log | `status()`/`redact()` mask เหลือ 4 ตัวท้าย | — |
| S5 | มีปุ่มหยุดทันที | **Kill switch** → AI ห้ามใช้เงินทุกกรณี (ยัง "หยุด" ad ได้) | log `KILL_SWITCH` |
| S6 | งบขยายมั่วไม่ได้ | `daily_hard_cap` ถูก `clamp` ด้วย `SYSTEM_MAX_DAILY_CAP` แม้มี token | log `UPDATE_GUARDRAIL` |
| — | CORS | อนุญาตเฉพาะ `FRONTEND_ORIGIN` (ห้าม `*`) กันเว็บอื่นเรียกจากเบราว์เซอร์ | — |

ก่อนรันจริง ต้องสร้าง 2 ค่านี้ใส่ `.env` (ไม่ตั้ง = ระบบล็อกตัวเอง):
```bash
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"   # → SECURITY_KEY
python -c "import secrets;print(secrets.token_urlsafe(24))"                                 # → ADMIN_TOKEN
```
เข้าเว็บครั้งแรก กรอก `ADMIN_TOKEN` ที่หน้าจอ login เพื่อปลดล็อกแดชบอร์ด

## เส้นทางต่อไป (v2)
- ✅ (ทำแล้ว) auth gate + encryption-at-rest + kill switch + cap ceiling + CORS lock + redaction + **rate-limit**
- ✅ (ทำแล้ว) **sync insight จาก Meta → `ad_sets`/`spend_ledger`** ทุก 30 นาที + ปุ่ม "🔄 Sync Meta"
- ✅ (ทำแล้ว) **AI ยิง Meta จริง** (pause/ปรับงบ) เฉพาะตอน LIVE mode — dry-run จำลองอย่างเดียว
- ✅ (ทำแล้ว) **kill switch สั่ง PAUSED บน Meta จริง** (emergency_pause_all)
- ให้ AI เสนอ creative 2 ตัว A/B test (ใช้ skill สูตรโพสต์ป้ายยาที่มีอยู่)
- ระบบ notify ผลลัพธ์ผ่าน LINE bot (@177otybx)
- ทดสอบ penetration/abuse-case เพิ่มเติม (prompt injection จาก insight/comments)
- เก็บ audit log นอกเครื่อง (offsite) กันผู้โจมตีลบหลักฐาน
