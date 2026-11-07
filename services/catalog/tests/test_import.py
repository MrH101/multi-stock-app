import io
import time
from datetime import date

from tests.conftest import OTHER_SUPPLIER, PHARMACY, SUPPLIER

SHEET = """Zim Pharma Wholesale - Price list November
Item Code,Description,Generic,Strength,Form,Pack,MCAZ Reg No,Category,Price (USD),Batch No,Exp Date,Qty
AMX500,Amoxil,Amoxicillin,500mg,Caps,100s,2009/7.3/4567,PP,"US$12.50",AMX-1,03/2030,200
PAN500,Panado,Paracetamol,500mg,tabs,24s,,HR,1.80,,,
BAD1,Broken,,,,,,,abc,,,
AMX500,Duplicate,,,,,,,1.00,,,
EXP1,Old Stock,,,,,,P,2.00,OLD-1,01/01/2020,10
CAT1,Weird,,,,,,ZZ,2.00,,,
"""


def upload(client, content, name="prices.csv", commit=False, headers=SUPPLIER):
    data = content.encode() if isinstance(content, str) else content
    return client.post("/supplier/imports", headers=headers, params={"commit": commit},
                       files={"file": (name, io.BytesIO(data), "text/csv")})


def products(client, headers=SUPPLIER):
    return {p["sku"]: p for p in client.get("/supplier/products", headers=headers).json()["items"]}


def test_preview_reports_every_row_without_changing_anything(client):
    r = upload(client, SHEET)
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["committed"] is False
    assert rep["summary"] == {"total": 6, "create": 2, "update": 0, "unchanged": 0, "error": 4, "batches_added": 1}
    by_row = {x["row"]: x for x in rep["rows"]}
    assert by_row[3]["action"] == "create" and by_row[3]["batch"] == "added"  # row 3 in the spreadsheet
    assert "not a number" in by_row[5]["messages"][0]
    assert "more than once" in by_row[6]["messages"][0]
    assert "expired" in by_row[7]["messages"][0]
    assert "MCAZ category" in by_row[8]["messages"][0]
    assert rep["columns"]["Item Code"] == "sku" and rep["columns"]["Price (USD)"] == "unit_price"
    assert products(client) == {}


def test_commit_creates_products_and_opening_stock(client):
    rep = upload(client, SHEET, commit=True).json()
    assert rep["committed"] and rep["summary"]["create"] == 2
    ps = products(client)
    amx = ps["AMX500"]
    assert amx["unit_price"] == "12.50" and amx["dosage_form"] == "CAPSULE" and amx["schedule"] == "PP"
    assert amx["mcaz_registration_number"] == "2009/7.3/4567" and amx["stock_available"] == 200
    assert amx["nearest_expiry"] == "2030-03-31"  # month-only expiry = end of month
    assert ps["PAN500"]["dosage_form"] == "TABLET" and ps["PAN500"]["stock_available"] == 0
    # pharmacies can order it straight away
    assert client.get("/products", headers=PHARMACY, params={"q": "amoxil"}).json()["items"][0]["stock_available"] == 200


def test_weekly_price_update_only_touches_what_changed(client):
    upload(client, SHEET, commit=True)
    client.patch(f"/products/{products(client)['PAN500']['id']}", headers=SUPPLIER, json={"description": "keep me"})
    update = "Code,Name,Price\nAMX500,Amoxil,13.75\nPAN500,Panado,1.80\nNEW1,Ventolin Inhaler,6.00\n"
    rep = upload(client, update, commit=True).json()
    assert rep["summary"] == {"total": 3, "create": 1, "update": 1, "unchanged": 1, "error": 0, "batches_added": 0}
    amx_row = next(r for r in rep["rows"] if r["sku"] == "AMX500")
    assert "price 12.50 → 13.75" in amx_row["messages"]
    ps = products(client)
    assert ps["AMX500"]["unit_price"] == "13.75"
    assert ps["AMX500"]["schedule"] == "PP" and ps["AMX500"]["generic_name"] == "Amoxicillin"  # not wiped
    assert ps["PAN500"]["description"] == "keep me"
    assert ps["AMX500"]["stock_available"] == 200


def test_reimporting_a_batch_does_not_double_count(client):
    upload(client, SHEET, commit=True)
    rep = upload(client, SHEET, commit=True).json()
    row = next(r for r in rep["rows"] if r["sku"] == "AMX500")
    assert row["batch"] == "exists" and "stock adjustment" in row["messages"][-1]
    assert products(client)["AMX500"]["stock_available"] == 200


def test_skus_are_per_supplier(client):
    upload(client, SHEET, commit=True)
    rep = upload(client, "SKU,Name,Price\nAMX500,Their Amoxicillin,9.00\n", commit=True, headers=OTHER_SUPPLIER).json()
    assert rep["summary"]["create"] == 1
    assert products(client)["AMX500"]["name"] == "Amoxil"


def test_excel_upload_and_template(client):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["SKU", "Product Name", "Unit Price", "Expiry", "Batch", "Qty"])
    ws.append([1002, "Ciprobay 500mg", 9.0, date(2031, 6, 30), "CIP-9", 50.0])
    buf = io.BytesIO()
    wb.save(buf)
    rep = upload(client, buf.getvalue(), name="list.xlsx", commit=True).json()
    assert rep["summary"]["create"] == 1 and rep["summary"]["batches_added"] == 1, rep
    assert products(client)["1002"]["stock_available"] == 50  # Excel's 1002.0 stays "1002"

    t = client.get("/supplier/imports/template.csv", headers=SUPPLIER)
    assert t.status_code == 200 and t.text.startswith("SKU,Name") and "attachment" in t.headers["content-disposition"]
    assert upload(client, t.text, commit=False).json()["summary"]["error"] == 0


def test_bad_files_get_clear_errors(client):
    assert "required column" in upload(client, "Name,Pack\nX,1\n").json()["detail"]
    assert "header row" in upload(client, "just,one\nfoo,bar\n").json()["detail"]
    assert "xlsx or CSV" in upload(client, b"\xd0\xcf", name="old.xls").json()["detail"]
    assert upload(client, SHEET, headers=PHARMACY).status_code == 403


def test_two_thousand_line_price_list(client):
    lines = ["SKU,Name,Generic,Strength,Price,Batch,Expiry,Qty"]
    lines += [f"S{i},Product {i},Generic {i % 50},{i % 5 * 100 + 100}mg,{1 + i % 90}.25,B{i},31/12/2030,{i % 300 + 1}"
              for i in range(2000)]
    t = time.perf_counter()
    rep = upload(client, "\n".join(lines), commit=True).json()
    elapsed = time.perf_counter() - t
    assert rep["summary"]["create"] == 2000 and rep["summary"]["batches_added"] == 2000
    t = time.perf_counter()
    again = upload(client, "\n".join(lines).replace(".25,", ".50,"), commit=True).json()
    assert again["summary"]["update"] == 2000
    assert elapsed < 30 and time.perf_counter() - t < 30, elapsed
