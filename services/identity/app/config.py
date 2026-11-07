from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "identity"
    database_url: str = "sqlite:///./identity.db"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    # Seeded platform admin (created on first start if no admin exists).
    admin_email: str = "admin@multistock.app"
    admin_password: str = "ChangeMe123!"


settings = Settings()
