from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import LEGACY_SCHEDULE, DosageForm, MovementReason, Schedule


def _schedule(v):
    return LEGACY_SCHEDULE.get(v, v) if isinstance(v, str) else v


def _reg_no(v):
    if isinstance(v, str):
        v = " ".join(v.split()).upper()
        return v or None
    return v


class ProductBase(BaseModel):
    sku: str | None = Field(None, max_length=100)
    name: str = Field(min_length=2, max_length=255)
    generic_name: str | None = Field(None, max_length=255)
    strength: str | None = Field(None, max_length=100)
    dosage_form: DosageForm = DosageForm.OTHER
    pack_size: str | None = Field(None, max_length=100)
    manufacturer: str | None = Field(None, max_length=200)
    schedule: Schedule = Schedule.P
    mcaz_registration_number: str | None = Field(None, max_length=60, description="MCAZ product registration number")
    unit_price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field("USD", min_length=3, max_length=3)
    description: str | None = None
    reorder_level: int = Field(0, ge=0)

    _norm_schedule = field_validator("schedule", mode="before")(_schedule)
    _norm_reg = field_validator("mcaz_registration_number", mode="before")(_reg_no)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    sku: str | None = None
    name: str | None = Field(None, min_length=2, max_length=255)
    generic_name: str | None = None
    strength: str | None = None
    dosage_form: DosageForm | None = None
    pack_size: str | None = None
    manufacturer: str | None = None
    schedule: Schedule | None = None
    mcaz_registration_number: str | None = Field(None, max_length=60)
    unit_price: Decimal | None = Field(None, gt=0)
    currency: str | None = Field(None, min_length=3, max_length=3)
    description: str | None = None
    reorder_level: int | None = Field(None, ge=0)
    is_active: bool | None = None

    _norm_schedule = field_validator("schedule", mode="before")(_schedule)
    _norm_reg = field_validator("mcaz_registration_number", mode="before")(_reg_no)


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_org_id: int
    supplier_name: str
    is_active: bool
    created_at: datetime
    stock_available: int = 0
    nearest_expiry: date | None = None


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int


class BatchCreate(BaseModel):
    batch_number: str = Field(min_length=1, max_length=100)
    expiry_date: date
    quantity: int = Field(gt=0)


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: int
    batch_number: str
    expiry_date: date
    quantity_available: int
    quantity_reserved: int


class PublicBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_number: str
    expiry_date: date
    quantity_available: int


class ProductDetail(ProductOut):
    batches: list[PublicBatchOut] = []


class StockAdjustment(BaseModel):
    change: int = Field(description="Positive to add stock, negative to remove")
    reason: MovementReason = MovementReason.ADJUSTMENT
    note: str | None = Field(None, max_length=500)


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    change: int
    reason: MovementReason
    reference: str | None
    note: str | None
    created_at: datetime


class ExpiringBatch(BaseModel):
    batch_id: int
    product_id: int
    product_name: str
    batch_number: str
    expiry_date: date
    days_to_expiry: int
    quantity_available: int


class LowStockProduct(BaseModel):
    product_id: int
    product_name: str
    stock_available: int
    reorder_level: int


class InventoryAlerts(BaseModel):
    expiring: list[ExpiringBatch]
    expired: list[ExpiringBatch]
    low_stock: list[LowStockProduct]


# ---- internal (service-to-service)
class ReservationLineIn(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class ReservationRequest(BaseModel):
    order_ref: str
    lines: list[ReservationLineIn] = Field(min_length=1)


class Allocation(BaseModel):
    batch_number: str
    expiry_date: date
    quantity: int


class ReservedLine(BaseModel):
    product_id: int
    product_name: str
    generic_name: str | None
    strength: str | None
    pack_size: str | None
    supplier_org_id: int
    supplier_name: str
    unit_price: Decimal
    currency: str
    quantity: int
    schedule: Schedule | None = None
    mcaz_registration_number: str | None = None
    allocations: list[Allocation]


class ReservationResult(BaseModel):
    order_ref: str
    lines: list[ReservedLine]


class InternalProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    supplier_org_id: int
    supplier_name: str
    unit_price: Decimal
    currency: str
    is_active: bool
