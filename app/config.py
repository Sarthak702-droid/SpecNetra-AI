from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = Field(default="test-key", repr=False)
    plan_mode: str = "fixture"  # "ai" or "fixture" for offline testability

    api_base_url: str = "http://localhost:8001"
    web_base_url: str = "http://localhost:3000"
    allowed_target_hosts: list[str] | str = ["localhost", "127.0.0.1", "demo-api", "demo-web"]

    test_user_email: str = "tester@example.test"
    test_user_password: str = Field(default="SecretPassword123!", repr=False)

    test_timeout_ms: int = 15000
    max_retries: int = 2
    max_tests_per_run: int = 10
    browser_headless: bool = True
    output_dir: str = "output"
    target_environment: str = "staging"
    demo_bug_mode: str = ""
    ui_engine: str = "python"  # "python" or "midscene"
    midscene_worker_port: int = 0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("allowed_target_hosts", mode="after")
    @classmethod
    def normalize_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v


settings = Settings()
