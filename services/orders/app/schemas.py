from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

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
    currency: str = Field("USD", min_length=3, max_length=3)


class BudgetOut(BaseModel):
    period: date
    amount: Decimal
    currency: str
    committed: Decimal
    remaining: Decimal
    percent_used: float
    is_set: bool


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
