from multistock_common.settings import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "agent"
    database_url: str = "sqlite:///./agent.db"

    # Where the other services live (service-to-service, never through the public gateway).
    identity_url: str = "http://localhost:8001"
    catalog_url: str = "http://localhost:8002"
    orders_url: str = "http://localhost:8003"
    notifications_url: str = "http://localhost:8004"

    # ---- monitoring loop
    monitor_enabled: bool = True
    monitor_interval_seconds: int = 900
    monitor_initial_delay_seconds: int = 20
    max_notifications_per_org_per_run: int = 5

    # ---- thresholds (deterministic rules decide *what* is wrong; the model only explains it)
    expiry_warning_days: int = 90
    expiry_critical_days: int = 30
    cover_warning_days: int = 14  # days of stock left at current demand
    cover_critical_days: int = 7
    reorder_target_days: int = 30  # suggested reorder brings cover up to this many days
    supplier_demand_days: int = 30
    pharmacy_demand_days: int = 90
    budget_warning_percent: float = 80
    budget_info_percent: float = 50
    order_review_sla_hours: int = 24  # SUBMITTED -> ACCEPTED/REJECTED
    order_dispatch_sla_hours: int = 48  # ACCEPTED -> DISPATCHED
    order_delivery_sla_hours: int = 72  # DISPATCHED -> DELIVERED

    # ---- Caimex (OpenAI-compatible gateway) for digests and the assistant
    caimex_api_key: str = ""
    caimex_base_url: str = "https://api.caimex.ai/v1"
    caimex_model: str = "gpt-5.4-mini-2026-03-17"
    caimex_fallback_models: list[str] = ["gpt-5-mini", "mistral-small-latest"]
    caimex_timeout_seconds: float = 45
    digest_min_interval_minutes: int = 60
    digest_max_per_run: int = 50
    assistant_max_steps: int = 6


settings = Settings()
