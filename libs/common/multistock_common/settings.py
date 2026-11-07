from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Settings shared by every service. Values come from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "service"
    environment: str = "development"
    database_url: str = "sqlite:///./service.db"
    # Shared HS256 secret used to verify access tokens issued by the identity service.
    jwt_secret: str = "dev-only-change-me-dev-only-change-me"
    jwt_algorithm: str = "HS256"
    # Token used for service-to-service calls on /internal endpoints.
    service_token: str = "dev-service-token"
    # Redis stream used as the event bus. Empty string disables publishing (local dev/tests).
    redis_url: str = ""
    event_stream: str = "multistock.events"
    # Local development without Redis: deliver events by HTTP to this URL instead.
    event_webhook_url: str = ""
    cors_origins: list[str] = ["http://localhost:5173"]

    def assert_production_safe(self) -> None:
        if self.environment == "production":
            if self.jwt_secret.startswith("dev-") or self.service_token.startswith("dev-"):
                raise RuntimeError("Refusing to start in production with development secrets")
