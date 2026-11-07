from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "orders"
    database_url: str = "sqlite:///./orders.db"
    catalog_url: str = "http://localhost:8002"


settings = Settings()
