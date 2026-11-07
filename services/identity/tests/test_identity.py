PHARMACY = {
    "org_type": "PHARMACY", "org_name": "Avenues Pharmacy", "license_number": "MCAZ-P-001",
    "full_name": "Tendai Moyo", "email": "tendai@avenues.co.zw", "password": "Secret123!", "city": "Harare",
}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_and_me(client):
    r = client.post("/auth/register", json=PHARMACY)
    assert r.status_code == 201, r.text
    assert r.json()["organization"]["type"] == "PHARMACY"
    assert r.json()["user"]["role"] == "OWNER"

    r = client.post("/auth/login", json={"email": "TENDAI@avenues.co.zw", "password": "Secret123!"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/me", headers=auth(token)).json()
    assert me["organization"]["name"] == "Avenues Pharmacy"

    refreshed = client.post("/auth/refresh", json={"refresh_token": r.json()["refresh_token"]})
    assert refreshed.status_code == 200
    # access tokens cannot be used as refresh tokens
    assert client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401


def test_duplicate_and_bad_password(client):
    client.post("/auth/register", json=PHARMACY)
    assert client.post("/auth/register", json=PHARMACY).status_code == 409
    assert client.post("/auth/login", json={"email": PHARMACY["email"], "password": "wrong-pass"}).status_code == 401


def test_team_management_is_owner_only_and_org_scoped(client):
    owner = client.post("/auth/register", json=PHARMACY).json()["access_token"]
    r = client.post("/users", headers=auth(owner), json={
        "email": "staff@avenues.co.zw", "full_name": "Staff One", "role": "STAFF", "password": "Secret123!"})
    assert r.status_code == 201
    staff = client.post("/auth/login", json={"email": "staff@avenues.co.zw", "password": "Secret123!"}).json()["access_token"]
    assert client.post("/users", headers=auth(staff), json={
        "email": "x@y.co.zw", "full_name": "X Y", "password": "Secret123!"}).status_code == 403
    assert len(client.get("/users", headers=auth(staff)).json()) == 2

    other = client.post("/auth/register", json={**PHARMACY, "email": "o@o.co.zw", "license_number": "MCAZ-2"}).json()
    assert client.patch(f"/users/{r.json()['id']}", headers=auth(other["access_token"]),
                        json={"is_active": False}).status_code == 404


def test_admin_can_verify_suppliers(client):
    sup = client.post("/auth/register", json={**PHARMACY, "org_type": "SUPPLIER", "email": "s@s.co.zw",
                                              "license_number": "MCAZ-W-9", "org_name": "Pharma Wholesale"}).json()
    admin = client.post("/auth/login", json={"email": "admin@multistock.app", "password": "ChangeMe123!"}).json()["access_token"]
    org_id = sup["organization"]["id"]
    assert client.patch(f"/admin/organizations/{org_id}", headers=auth(sup["access_token"]), json={"verified": True}).status_code == 403
    r = client.patch(f"/admin/organizations/{org_id}", headers=auth(admin), json={"verified": True})
    assert r.json()["verified"] is True
    suppliers = client.get("/organizations?type=SUPPLIER", headers=auth(admin)).json()
    assert [o["name"] for o in suppliers] == ["Pharma Wholesale"]
