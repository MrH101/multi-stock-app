from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .models import Method, PayStatus


class MerchantIn(BaseModel):
    paynow_enabled: bool = False
    paynow_integration_id: str | None = Field(None, max_length=40, pattern=r"^\d*$")
    # Write-only: send a new key to change it, omit to keep the stored one.
    paynow_integration_key: str | None = Field(None, min_length=8, max_length=100)
    bank_name: str | None = Field(None, max_length=120)
    bank_account_name: str | None = Field(None, max_length=200)
    bank_account_number: str | None = Field(None, max_length=60)
    bank_branch: str | None = Field(None, max_length=120)
    payment_instructions: str | None = Field(None, max_length=500)


class MerchantOut(BaseModel):
    currency: str
    paynow_enabled: bool
    paynow_integration_id: str | None
    paynow_integration_key_masked: str | None
    bank_name: str | None
    bank_account_name: str | None
    bank_account_number: str | None
    bank_branch: str | None
    payment_instructions: str | None


class BankDetails(BaseModel):
    bank_name: str | None
    bank_account_name: str | None
    bank_account_number: str | None
    bank_branch: str | None
    payment_instructions: str | None


class PaymentOptions(BaseModel):
    order_number: str
    amount: Decimal
    currency: str
    payment_status: str | None
    methods: list[Method]
    bank: BankDetails | None
    reason: str | None = None  # why nothing can be paid right now


class PaymentIn(BaseModel):
    order_number: str = Field(max_length=40)
    method: Method
    phone: str | None = Field(None, max_length=20)


class ProofOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    content_type: str
    size: int
    bank_reference: str | None
    uploaded_by: str
    reviewed_by: str | None
    review_note: str | None
    created_at: datetime


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    reference: str
    order_id: int
    order_number: str
    amount: Decimal
    currency: str
    method: Method
    status: PayStatus
    phone: str | None
    provider_reference: str | None
    provider_status: str | None
    redirect_url: str | None
    instructions: str | None
    innbucks_code: str | None
    innbucks_expires: str | None
    paid_at: datetime | None
    created_by_name: str
    note: str | None
    error: str | None
    created_at: datetime
    proofs: list[ProofOut]


class Review(BaseModel):
    accept: bool
    note: str | None = Field(None, max_length=500)
