"""Load config from .env — ผู้ใช้กรอกแค่ key/cap ที่นี่ที่เดียว"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Meta
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_AD_ACCOUNT_ID: str = ""
    META_PAGE_ID: str = ""
    META_PAGE_ACCESS_TOKEN: str = ""
    META_MARKETING_TOKEN: str = ""

    # AI
    AI_PROVIDER: str = "openai"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"
    AI_BASE_URL: str = "https://api.openai.com/v1"

    # Guardrails
    GUARD_DAILY_HARD_CAP: float = 1000
    GUARD_PER_CAMPAIGN_CAP: float = 400
    GUARD_VELOCITY_WINDOW_MIN: int = 120
    GUARD_VELOCITY_MAX_PCT: int = 30
    GUARD_MIN_ROAS: float = 1.5
    GUARD_LEARNING_MIN_CONV: int = 50
    GUARD_DRY_RUN: bool = True

    DATABASE_URL: str = "postgresql://ads:ads@db:5432/ads_autopilot"
    LOG_LEVEL: str = "INFO"

    # ---- Security (fail-closed defaults) ----
    SECURITY_KEY: str = ""        # Fernet key สำหรับ เข้ารหัส secret ใน DB
    ADMIN_TOKEN: str = ""         # ถ้าตั้ง = ต้องส่ง token นี้มาทุก call
    ADMIN_TOKEN_HASH: str = ""    # ทางเลือกที่ปลอดภัยกว่า (เก็บ hash แทนค่าจริง)
    FRONTEND_ORIGIN: str = "http://localhost:3000"  # CORS ล็อกไว้แค่นี้ (ห้าม *)
    SYSTEM_MAX_DAILY_CAP: float = 5000  # เพดานสูงสุดของ daily_hard_cap (ขยายเองเกินนี้ไม่ได้)

    # ---- User auth / OAuth ----
    AUTH_SECRET: str = ""         # ลายเซ็น session token (ว่าง = ใช้ SECURITY_KEY แทน)
    REDIRECT_BASE: str = "http://localhost:8000"  # base URL ของ backend สำหรับ OAuth callback
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    FACEBOOK_CLIENT_ID: str = ""
    FACEBOOK_CLIENT_SECRET: str = ""

    @property
    def graph_base(self) -> str:
        return "https://graph.facebook.com/v21.0"

    def meta_token(self) -> str:
        # marketing token สำคัญที่สุดสำหรับยิงแอด; fallback เป็น page token
        return self.META_MARKETING_TOKEN or self.META_PAGE_ACCESS_TOKEN

    def keys_provided(self) -> dict:
        """ใช้ตรวจตอน connect: บอกผู้ใช้ว่า key ไหนยังขาดอยู่"""
        return {
            "META_APP_ID": bool(self.META_APP_ID),
            "META_AD_ACCOUNT_ID": bool(self.META_AD_ACCOUNT_ID),
            "META_MARKETING_TOKEN": bool(self.meta_token()),
            "AI_API_KEY": bool(self.AI_API_KEY) or self.AI_PROVIDER == "ollama",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
