from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "payments"
    database_url: str = "sqlite:///./payments.db"
    orders_url: str = "http://localhost:8003"

    # Encrypts suppliers' Paynow integration keys at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    payments_secret_key: str = "dev-only-insecure-key"
    # Public origin Paynow redirects the browser back to and posts results to (the gateway).
    public_base_url: str = "http://localhost:8080"
    paynow_base_url: str = "https://www.paynow.co.zw"
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 5 * 1024 * 1024
    poll_interval_seconds: int = 60
    pending_timeout_hours: int = 24

    def assert_production_safe(self) -> None:
        super().assert_production_safe()
        if self.environment == "production" and self.payments_secret_key.startswith("dev-"):
            raise RuntimeError("Set PAYMENTS_SECRET_KEY before running payments in production")


settings = Settings()
