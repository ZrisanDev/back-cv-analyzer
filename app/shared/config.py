from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Database ──────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/cv_analyzer"
    )
    postgres_db: str = "cv_analyzer"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # ── Auth ──────────────────────────────────────────────
    secret_key: str = "change-me-to-a-strong-random-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── MercadoPago ───────────────────────────────────────
    mercadopago_access_token: str = ""
    mercadopago_public_key: str = ""
    mercadopago_webhook_secret: str = ""

    # ── AI Providers ──────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # ── AI Service ────────────────────────────────────────
    ai_max_retries: int = 2
    ai_timeout_seconds: int = 120

    # ── Email ─────────────────────────────────────────────
    gmail_email: str = ""
    gmail_app_password: str = ""

    # ── Billing ───────────────────────────────────────────
    free_analysis_limit: int = 3
    analysis_price_usd: float = 2.99

    # ── CORS ──────────────────────────────────────────────
    cors_origins: str = "https://astounding-mermaid-567c0a.netlify.app,http://localhost:3000,http://localhost:5173"

    # ── Frontend ──────────────────────────────────────────
    frontend_base_url: str = "https://astounding-mermaid-567c0a.netlify.app"

    # ── App ───────────────────────────────────────────────
    app_version: str = "0.1.0"


settings = Settings()
