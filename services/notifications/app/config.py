from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "notifications"
    database_url: str = "sqlite:///./notifications.db"
    consumer_group: str = "notifications"
    consumer_name: str = "notifications-1"


settings = Settings()
