-- ============================================================================
--  FB Ads Autopilot schema
-- ============================================================================
CREATE TABLE IF NOT EXISTS guardrail_config (
    id                SERIAL PRIMARY KEY,
    daily_hard_cap    NUMERIC(12,2) NOT NULL,      -- THB / วัน (hard, AI แก้เองไม่ได้)
    per_campaign_cap  NUMERIC(12,2) NOT NULL,
    velocity_window_min INT NOT NULL,              -- นาที
    velocity_max_pct  INT NOT NULL,                -- % ของงบรายวัน
    min_roas          NUMERIC(6,3) NOT NULL,
    learning_min_conv INT NOT NULL,
    dry_run           BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS campaigns (
    id                BIGSERIAL PRIMARY KEY,
    meta_campaign_id  TEXT UNIQUE,
    name              TEXT NOT NULL,
    product           TEXT,                         -- สินค้าที่โปรโมต (ใช้หมุน)
    status            TEXT NOT NULL DEFAULT 'DRAFT', -- DRAFT/ACTIVE/PAUSED/ARCHIVED
    daily_budget      NUMERIC(12,2) NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ad_sets (
    id                BIGSERIAL PRIMARY KEY,
    campaign_id       BIGINT REFERENCES campaigns(id),
    meta_adset_id     TEXT UNIQUE,
    name              TEXT NOT NULL,
    product           TEXT,                         -- สินค้าที่ ad set นี้โปรโมต (ใช้หมุน)
    status            TEXT NOT NULL DEFAULT 'DRAFT',
    daily_budget      NUMERIC(12,2) NOT NULL DEFAULT 0,
    spend             NUMERIC(12,2) NOT NULL DEFAULT 0,
    conversions       INT NOT NULL DEFAULT 0,
    revenue           NUMERIC(12,2) NOT NULL DEFAULT 0,
    in_learning       BOOLEAN NOT NULL DEFAULT TRUE,
    audience_sig      TEXT,                         -- fingerprint กัน audience ทับซ้อน
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS creatives (
    id                BIGSERIAL PRIMARY KEY,
    ad_set_id         BIGINT REFERENCES ad_sets(id),
    meta_creative_id  TEXT UNIQUE,
    content_sig       TEXT,                         -- กัน creative ซ้ำ
    is_winning        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- บันทึกการใช้เงินทุกครั้งที่ sync มา (ใช้คำนวณ velocity + spend วันนี้)
CREATE TABLE IF NOT EXISTS spend_ledger (
    id                BIGSERIAL PRIMARY KEY,
    ad_set_id         BIGINT REFERENCES ad_sets(id),
    spent             NUMERIC(12,2) NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_time ON spend_ledger (occurred_at);

-- Audit log: ทุกการตัดสินใจของ AI + คำสั่ง guardrail (โปร่งใสย้อนดูได้)
CREATE TABLE IF NOT EXISTS ai_decisions (
    id                BIGSERIAL PRIMARY KEY,
    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
    action            TEXT NOT NULL,                -- e.g. RAISE_BUDGET / PAUSE / CREATE_ADSET
    target            TEXT,                         -- ad set / campaign
    proposed_value    TEXT,
    verdict           TEXT NOT NULL,                -- ALLOW / BLOCK / PAUSE / WOULD_ALLOW(dry-run)
    reason            TEXT NOT NULL,                -- ผูกกับข้อ guardrail ที่ใช้
    guardrail_rule    TEXT,
    applied           BOOLEAN NOT NULL DEFAULT FALSE
);

-- seed default guardrail row (จะถูก refresh จากค่า env ตอนบูต)
INSERT INTO guardrail_config
    (daily_hard_cap, per_campaign_cap, velocity_window_min, velocity_max_pct,
     min_roas, learning_min_conv, dry_run)
VALUES (1000, 400, 120, 30, 1.5, 50, TRUE)
ON CONFLICT DO NOTHING;

-- ผู้ใช้ (login / register)
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT UNIQUE,
    name            TEXT,
    password_hash   TEXT,
    provider        TEXT DEFAULT 'password',   -- password | google | facebook
    provider_id     TEXT,
    role            TEXT DEFAULT 'user',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
