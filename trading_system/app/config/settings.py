from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    # Environment Configuration
    ENVIRONMENT: str = Field(default="PAPER", description="PAPER or LIVE")
    
    # Database Configuration (V2 Upgrade: Migrating from SQLite to PostgreSQL)
    # This matches the docker-compose.yml defaults
    DATABASE_URL: str = Field(default="postgresql+psycopg2://quant:quantpassword@localhost:5432/trading_db", description="Database connection string")
    
    # Broker Configuration
    PAPER_API_KEY: Optional[str] = None
    PAPER_API_SECRET: Optional[str] = None
    
    # LIVE TRADING SAFETY SWITCH
    LIVE_TRADING_ENABLED: bool = Field(
        default=False, 
        description="Must be explicitly True to enable live execution. DO NOT auto-switch."
    )
    LIVE_API_KEY: Optional[str] = None
    LIVE_API_SECRET: Optional[str] = None
    
    # Risk Limits (Global Baseline)
    MAX_PORTFOLIO_EXPOSURE: float = Field(default=1.0, description="Max gross exposure")
    MAX_SINGLE_POSITION: float = Field(default=0.20, description="Max weight for a single ticker")
    MAX_DAILY_LOSS: float = Field(default=0.05, description="Kill switch daily loss threshold (5%)")

    # Notifications (Discord & Telegram)
    DISCORD_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    class Config:
        env_file = ("../.env", ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
