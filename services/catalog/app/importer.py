"""Price-list import for wholesalers (issue #5).

Wholesalers already keep their catalogue in a spreadsheet and send updated price lists weekly. This turns
such a file (CSV or Excel) into product upserts keyed by SKU, plus optional opening stock per batch.
Parsing is forgiving about headers, dates, prices and dosage-form spellings; every row gets a clear
outcome so the supplier can fix their sheet and re-upload.
"""
import calendar
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import stock
from .models import LEGACY_SCHEDULE, Batch, DosageForm, MovementReason, Product, Schedule

MAX_ROWS = 10_000
MAX_BYTES = 5 * 1024 * 1024

# Canonical field -> header spellings seen in real price lists (compared lower-case, punctuation removed).
HEADERS: dict[str, tuple[str, ...]] = {
    "sku": ("sku", "code", "item code", "product code", "stock code", "item no", "item number", "nappi"),
    "name": ("name", "product", "product name", "item", "item name", "description", "brand", "trade name"),
    "generic_name": ("generic", "generic name", "inn", "active ingredient", "molecule"),
    "strength": ("strength", "dose", "dosage strength"),
    "dosage_form": ("form", "dosage form", "formulation"),
    "pack_size": ("pack", "pack size", "packsize", "unit of sale", "uom"),
    "manufacturer": ("manufacturer", "mfr", "brand owner", "supplier brand"),
    "schedule": ("schedule", "category", "mcaz category", "class", "supply category"),
    "mcaz_registration_number": ("mcaz", "mcaz reg", "mcaz reg no", "mcaz registration", "mcaz registration number",
                                 "reg no", "registration number", "registration no"),
    "unit_price": ("price", "unit price", "selling price", "price usd", "usd price", "price us", "trade price", "cost"),
    "currency": ("currency", "ccy"),
    "reorder_level": ("reorder", "reorder level", "min stock", "minimum stock"),
    "batch_number": ("batch", "batch no", "batch number", "lot", "lot no", "lot number"),
    "expiry_date": ("expiry", "expiry date", "exp", "exp date", "expires", "best before"),
    "quantity": ("qty", "quantity", "stock", "stock qty", "quantity on hand", "soh", "on hand"),
}
REQUIRED = ("sku", "name", "unit_price")

FORMS = [
    (("tab", "tabs", "tablet", "tablets", "caplet", "caplets"), DosageForm.TABLET),
    (("cap", "caps", "capsule", "capsules"), DosageForm.CAPSULE),
    (("syr", "syrup", "elixir", "mixture"), DosageForm.SYRUP),
    (("susp", "suspension"), DosageForm.SUSPENSION),
    (("vial", "vials", "inj vial"), DosageForm.INJECTION_VIAL),
    (("inj", "injection", "amp", "ampoule", "ampoules", "amps"), DosageForm.INJECTION_AMPOULE),
    (("pen", "pens", "penfill"), DosageForm.PEN),
    (("cream", "oint", "ointment", "gel", "lotion"), DosageForm.CREAM_OINTMENT),
    (("drops", "eye drops", "ear drops", "gtt"), DosageForm.DROPS),
    (("inhaler", "inh", "mdi", "evohaler", "accuhaler"), DosageForm.INHALER),
    (("supp", "suppository", "suppositories"), DosageForm.SUPPOSITORY),
    (("pess", "pessary", "pessaries"), DosageForm.PESSARY),
    (("surgical", "dressing", "bandage", "gloves", "syringe", "syringes"), DosageForm.SURGICAL),
]


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(header).lower().replace("_", " ").replace(".", " ")).strip()


def map_headers(headers: list[str]) -> tuple[dict[int, str], list[str]]:
    lookup = {_key(alias): name for name, aliases in HEADERS.items() for alias in (*aliases, name)}
    mapping, unknown = {}, []
    for i, h in enumerate(headers):
        name = lookup.get(" ".join(_key(h).split()))
        if name and name not in mapping.values():
            mapping[i] = name
        elif str(h).strip():
            unknown.append(str(h).strip())
    return mapping, unknown


def read_rows(filename: str, content: bytes) -> list[list]:
    if len(content) > MAX_BYTES:
        raise ValueError("File is larger than 5 MB. Split it into smaller files.")
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ValueError("This Excel file could not be opened. Save it as .xlsx or CSV and try again.") from exc
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    elif name.endswith((".csv", ".txt")) or not name:
        text = None
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Could not read the file's text encoding. Save it as CSV (UTF-8).")
        dialect = csv.excel
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            pass
        rows = list(csv.reader(io.StringIO(text), dialect))
    elif name.endswith(".xls"):
        raise ValueError("Old .xls files aren't supported. In Excel choose Save As → .xlsx or CSV.")
    else:
        raise ValueError("Upload a .csv or .xlsx file.")
    return rows


def parse_price(v) -> Decimal:
    if isinstance(v, (int, float, Decimal)):
        d = Decimal(str(v))
    else:
        s = re.sub(r"(?i)(us\$|usd|zig|zwg|zar|r|\$)", "", str(v or "")).replace(",", "").replace(" ", "")
        try:
            d = Decimal(s)
        except InvalidOperation:
            raise ValueError(f"price '{v}' is not a number")
    if d <= 0:
        raise ValueError("price must be above zero")
    return d.quantize(Decimal("0.01"))


def parse_date(v) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # month-only expiries ("03/2027", "Mar 2027") mean the last day of that month
    for fmt in ("%m/%Y", "%m-%Y", "%b %Y", "%B %Y", "%Y-%m", "%m/%y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.replace(day=calendar.monthrange(d.year, d.month)[1])
        except ValueError:
            pass
    raise ValueError(f"expiry '{s}' is not a date (use DD/MM/YYYY or MM/YYYY)")


def parse_form(v) -> DosageForm:
    s = _key(v or "")
    if not s:
        return DosageForm.OTHER
    if s.upper().replace(" ", "_") in DosageForm.__members__:
        return DosageForm[s.upper().replace(" ", "_")]
    for aliases, form in FORMS:
        if s in aliases or s.split()[0] in aliases:
            return form
    return DosageForm.OTHER


def parse_schedule(v) -> Schedule:
    s = re.sub(r"[^A-Z0-9_]", "", str(v or "").upper().replace(" ", "_"))
    if not s:
        return Schedule.P
    if s in LEGACY_SCHEDULE:
        return LEGACY_SCHEDULE[s]
    try:
        return Schedule(s)
    except ValueError:
        raise ValueError(f"category '{v}' is not an MCAZ category (PP, PIM, P, HR, CD or NON_MEDICINE)")


def parse_int(v, label: str) -> int:
    if v in (None, ""):
        return 0
    try:
        n = int(Decimal(str(v).replace(",", "").strip()))
    except InvalidOperation:
        raise ValueError(f"{label} '{v}' is not a whole number")
    if n < 0:
        raise ValueError(f"{label} cannot be negative")
    return n


def _text(v, limit: int) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))  # Excel turns codes like 1002 into 1002.0
    return s[:limit] or None


@dataclass
class RowResult:
    row: int
    sku: str | None
    name: str | None
    action: str  # create | update | unchanged | error
    messages: list[str] = field(default_factory=list)
    batch: str | None = None  # added | exists | None


@dataclass
class ImportReport:
    columns: dict[str, str]
    ignored_columns: list[str]
    rows: list[RowResult]
    committed: bool

    @property
    def summary(self) -> dict:
        out = {"total": len(self.rows), "create": 0, "update": 0, "unchanged": 0, "error": 0, "batches_added": 0}
        for r in self.rows:
            out[r.action] += 1
            out["batches_added"] += r.batch == "added"
        return out


PRODUCT_FIELDS = ("name", "generic_name", "strength", "dosage_form", "pack_size", "manufacturer", "schedule",
                  "mcaz_registration_number", "unit_price", "currency", "reorder_level")


def run_import(s: Session, supplier_org_id: int, supplier_name: str, user_id: int, filename: str, content: bytes,
               default_currency: str, commit: bool) -> ImportReport:
    rows = read_rows(filename, content)
    # header = first row with at least two recognised columns (sheets often start with a title row)
    header_at, mapping, ignored = None, {}, []
    for i, r in enumerate(rows[:15]):
        m, unknown = map_headers([c if c is not None else "" for c in r])
        if len(m) >= 2:
            header_at, mapping, ignored = i, m, unknown
            break
    if header_at is None:
        raise ValueError("Couldn't find a header row. The first row should name the columns (e.g. SKU, Name, Price).")
    missing = [f for f in REQUIRED if f not in mapping.values()]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(m.replace("_", " ") for m in missing))
    body = rows[header_at + 1:]
    if len(body) > MAX_ROWS:
        raise ValueError(f"The file has {len(body):,} rows; the limit is {MAX_ROWS:,} per upload.")

    existing = {p.sku: p for p in s.scalars(select(Product).where(Product.supplier_org_id == supplier_org_id))
                if p.sku}
    seen: set[str] = set()
    results: list[RowResult] = []
    today = date.today()

    for offset, raw in enumerate(body):
        line = header_at + offset + 2  # 1-based spreadsheet row number
        values = {name: raw[i] if i < len(raw) else None for i, name in mapping.items()}
        if all(v in (None, "") for v in values.values()):
            continue
        sku, name = _text(values.get("sku"), 100), _text(values.get("name"), 255)
        res = RowResult(row=line, sku=sku, name=name, action="error")
        results.append(res)
        try:
            if not sku:
                raise ValueError("SKU / code is required so later uploads can update this product")
            if sku in seen:
                raise ValueError(f"SKU {sku} appears more than once in this file")
            seen.add(sku)
            if not name or len(name) < 2:
                raise ValueError("name is required")
            data = {
                "name": name,
                "generic_name": _text(values.get("generic_name"), 255),
                "strength": _text(values.get("strength"), 100),
                "dosage_form": parse_form(values.get("dosage_form")),
                "pack_size": _text(values.get("pack_size"), 100),
                "manufacturer": _text(values.get("manufacturer"), 200),
                "schedule": parse_schedule(values.get("schedule")),
                "mcaz_registration_number": (_text(values.get("mcaz_registration_number"), 60) or "").upper() or None,
                "unit_price": parse_price(values.get("unit_price")),
                "currency": (_text(values.get("currency"), 3) or default_currency).upper(),
                "reorder_level": parse_int(values.get("reorder_level"), "reorder level"),
            }
            if data["currency"] not in ("USD", "ZWG", "ZAR"):
                raise ValueError(f"currency '{data['currency']}' must be USD, ZWG or ZAR")
            # columns that aren't in the file must not wipe what the supplier already entered in the app
            present = {f for f in PRODUCT_FIELDS if f in mapping.values() or f in ("name", "unit_price")}
            batch_no = _text(values.get("batch_number"), 100)
            batch = None
            if batch_no or values.get("expiry_date") or values.get("quantity") not in (None, "", 0):
                if not batch_no:
                    raise ValueError("stock columns need a batch number")
                expiry = parse_date(values.get("expiry_date"))
                qty = parse_int(values.get("quantity"), "quantity")
                if expiry <= today:
                    raise ValueError(f"batch {batch_no} expired on {expiry:%d/%m/%Y}; it can't be received")
                if qty <= 0:
                    raise ValueError(f"batch {batch_no} needs a quantity above zero")
                batch = (batch_no, expiry, qty)
        except ValueError as exc:
            res.messages.append(str(exc))
            continue

        product = existing.get(sku)
        if product is None:
            res.action = "create"
            if commit:
                product = Product(**data, sku=sku, supplier_org_id=supplier_org_id, supplier_name=supplier_name)
                s.add(product)
                s.flush()
                existing[sku] = product
        else:
            changes = {f: data[f] for f in present if getattr(product, f) != data[f]}
            if not product.is_active:
                changes["is_active"] = True
            res.action = "update" if changes else "unchanged"
            if changes:
                res.messages.append("changed: " + ", ".join(sorted(k.replace("_", " ") for k in changes)))
                if "unit_price" in changes:
                    res.messages.append(f"price {product.unit_price} → {data['unit_price']}")
            if commit:
                for k, v in changes.items():
                    setattr(product, k, v)

        if batch:
            batch_no, expiry, qty = batch
            current = None
            if product is not None and product.id:
                current = s.scalar(select(Batch).where(Batch.product_id == product.id, Batch.batch_number == batch_no))
            if current:
                res.batch = "exists"
                res.messages.append(f"batch {batch_no} already loaded; use a stock adjustment to change its quantity")
            else:
                res.batch = "added"
                if commit:
                    b = Batch(product_id=product.id, batch_number=batch_no, expiry_date=expiry, quantity_available=qty)
                    s.add(b)
                    s.flush()
                    stock.record(s, b, qty, MovementReason.RECEIVED, note=f"price list import: {filename}"[:500],
                                 user_id=user_id)
    if commit:
        s.commit()
    else:
        s.rollback()
    header = rows[header_at]
    return ImportReport(columns={str(header[i]).strip(): n for i, n in mapping.items()},
                        ignored_columns=ignored, rows=results, committed=commit)


TEMPLATE = ("SKU,Name,Generic name,Strength,Form,Pack size,Manufacturer,MCAZ category,MCAZ reg no,Price,Currency,"
            "Reorder level,Batch,Expiry,Qty\n"
            "AMX500,Amoxil,Amoxicillin,500mg,Capsule,100s,GSK,PP,2009/7.3/4567,12.50,USD,30,AMX-2401,31/03/2027,200\n"
            "PAN500,Panado,Paracetamol,500mg,Tablet,24s,Adcock,HR,,1.80,USD,50,,,\n")
