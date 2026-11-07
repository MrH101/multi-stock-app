from datetime import date, datetime
from decimal import Decimal

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import OrderStatus, PaymentMethod


class CheckoutLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100_000)


class CheckoutRequest(BaseModel):
    lines: list[CheckoutLine] = Field(min_length=1, max_length=500)
    delivery_address: str = Field(min_length=3, max_length=500)
    contact_name: str = Field(min_length=2, max_length=200)
    contact_phone: str = Field(min_length=5, max_length=50)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY
    notes: str | None = Field(None, max_length=2000)
    idempotency_key: str | None = Field(None, max_length=64, description="Resubmitting the same key returns the same orders")


class AllocationOut(BaseModel):
    batch_number: str
    expiry_date: date
    quantity: int


class OrderLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    product_name: str
    generic_name: str | None
    strength: str | None
    pack_size: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    schedule: str | None = None
    mcaz_registration_number: str | None = None
    allocations: list[AllocationOut]


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    status: OrderStatus
    note: str | None
    actor_name: str
    actor_org_name: str
    at: datetime


class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_number: str
    pharmacy_org_id: int
    pharmacy_name: str
    supplier_org_id: int
    supplier_name: str
    status: OrderStatus
    currency: str
    subtotal: Decimal
    amount_usd: Decimal | None = None
    fx_rates: dict[str, str] | None = None
    payment_status: str | None = "UNPAID"
    paid_at: datetime | None = None
    paid_via: str | None = None
    item_count: int = 0
    created_by_name: str
    created_at: datetime
    updated_at: datetime


class OrderOut(OrderSummaryOut):
    payment_method: PaymentMethod
    delivery_address: str
    contact_name: str
    contact_phone: str
    notes: str | None
    lines: list[OrderLineOut]
    history: list[OrderEventOut]
    allowed_transitions: list[OrderStatus] = []


class OrderPage(BaseModel):
    items: list[OrderSummaryOut]
    total: int
    page: int
    page_size: int


class StatusChange(BaseModel):
    status: OrderStatus
    note: str | None = Field(None, max_length=500)


class BudgetIn(BaseModel):
    amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    currency: Literal["USD", "ZWG", "ZAR"] = "USD"

    @field_validator("currency", mode="before")
    @classmethod
    def _upper(cls, v):
        return v.upper() if isinstance(v, str) else v


class BudgetOut(BaseModel):
    period: date
    amount: Decimal
    currency: str
    committed: Decimal
    remaining: Decimal
    percent_used: float
    is_set: bool
    # currencies of orders that could not be counted because no exchange rate is set yet
    unconverted_currencies: list[str] = []


class MonthPoint(BaseModel):
    month: str
    total: Decimal


class TopProduct(BaseModel):
    product_id: int
    product_name: str
    quantity: int
    total: Decimal


class DashboardSummary(BaseModel):
    counts: dict[OrderStatus, int]
    open_orders: int
    month_total: Decimal
    currency: str
    monthly: list[MonthPoint]
    top_products: list[TopProduct]
    unconverted_currencies: list[str] = []


class RatesIn(BaseModel):
    rates: dict[Literal["ZWG", "ZAR"], Annotated[Decimal, Field(gt=0, lt=1_000_000, decimal_places=6)]] = Field(
        min_length=1, description="Units of the currency per 1 USD")
    effective_date: date | None = None
    source: str | None = Field(None, max_length=120, description='e.g. "RBZ interbank 07/11"')


class RatesOut(BaseModel):
    base: str
    rates: dict[str, str]
    as_of: dict[str, date]
    updated_at: datetime | None
    source: dict[str, str | None]
    supported: list[str]


class RateHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    currency: str
    per_usd: Decimal
    effective_date: date
    source: str | None
    set_by: str | None
    created_at: datetime


class PaymentUpdate(BaseModel):
    payment_status: Literal["UNPAID", "PENDING", "AWAITING_CONFIRMATION", "PAID", "REFUNDED"]
    paid_via: str | None = Field(None, max_length=30)
    paid_at: datetime | None = None


class InternalOrder(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    order_number: str
    status: OrderStatus
    pharmacy_org_id: int
    pharmacy_name: str
    supplier_org_id: int
    supplier_name: str
    subtotal: Decimal
    currency: str
    payment_method: PaymentMethod
    payment_status: str | None
    created_by_user_id: int
