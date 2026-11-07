from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "catalog"
    database_url: str = "sqlite:///./catalog.db"
    default_currency: str = "USD"
    expiry_alert_days: int = 90


settings = Settings()
