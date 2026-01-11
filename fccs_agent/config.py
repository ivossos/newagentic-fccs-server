"""Configuration module using Pydantic Settings."""

from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class FCCSConfig(BaseSettings):
    """FCCS configuration with environment variable validation."""

    # FCCS Connection (optional in mock mode)
    fccs_url: Optional[str] = Field(None, alias="FCCS_URL")
    fccs_username: Optional[str] = Field(None, alias="FCCS_USERNAME")
    fccs_password: Optional[str] = Field(None, alias="FCCS_PASSWORD")
    fccs_api_version: str = Field("v3", alias="FCCS_API_VERSION")
    fccs_mock_mode: bool = Field(False, alias="FCCS_MOCK_MODE")

    # Database (SQLite for sessions + feedback)
    database_url: str = Field(
        "sqlite:///./data/fccs_agent_v2.db",
        alias="DATABASE_URL"
    )

    # Anthropic Claude API
    anthropic_api_key: Optional[str] = Field(None, alias="ANTHROPIC_API_KEY")

    # Claude Model for planning and reasoning
    model_id: str = Field("claude-opus-4-20250514", alias="MODEL_ID")

    # Server
    port: int = Field(8080, alias="PORT")
    cors_origins: str = Field(
        "http://localhost:3000,http://localhost:8080",
        alias="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins. Use '*' only for development."
    )
    fastmcp_host: str = Field("127.0.0.1", alias="FASTMCP_HOST")
    fastmcp_port: int = Field(8000, alias="FASTMCP_PORT")

    # Guardrails Configuration
    skip_confirmation: bool = Field(False, alias="FCCS_SKIP_CONFIRMATION")
    trusted_rules: str = Field(
        "Consolidate,Force Consolidate,Translate,Force Translate",
        alias="FCCS_TRUSTED_RULES",
        description="Comma-separated list of business rules that bypass confirmation"
    )
    trusted_operations: str = Field(
        "",
        alias="FCCS_TRUSTED_OPERATIONS",
        description="Comma-separated list of tool names that bypass confirmation (e.g., 'run_business_rule,copy_data')"
    )

    # Reinforcement Learning Configuration
    rl_enabled: bool = Field(True, alias="RL_ENABLED")
    rl_exploration_rate: float = Field(0.1, alias="RL_EXPLORATION_RATE")
    rl_learning_rate: float = Field(0.3, alias="RL_LEARNING_RATE")  # Increased for faster learning
    rl_discount_factor: float = Field(0.95, alias="RL_DISCOUNT_FACTOR")  # Higher future reward valuation
    rl_min_samples: int = Field(3, alias="RL_MIN_SAMPLES")  # Lower threshold for earlier RL activation

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


def load_config() -> FCCSConfig:
    """Load and validate configuration from environment variables."""
    config = FCCSConfig()

    # Validate FCCS credentials if not in mock mode
    if not config.fccs_mock_mode:
        if not all([config.fccs_url, config.fccs_username, config.fccs_password]):
            raise ValueError(
                "Missing FCCS credentials (FCCS_URL, FCCS_USERNAME, FCCS_PASSWORD) "
                "required when FCCS_MOCK_MODE is not true."
            )

    return config


# Global config instance
config = load_config()
