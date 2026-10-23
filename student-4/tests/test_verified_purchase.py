"""Shared session -> Reviews submission -> purpose-only Orders query -> real SQLite."""
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import requests
from itsdangerous import URLSafeTimedSerializer

from test_orders_crud_auth import ROOT, Reply, create, system as system
from test_orders_mcp import load_file

ORIGIN = "http://localhost:5001"
ISSUE_HEADERS = {"Origin": ORIGIN, "X-Reviews-Proof-Request": "1"}


@pytest.fixture
def integration(system, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / "student-1/backend"))
    # Student 1 uses generic package names: isolate imports from other services.
    with patch.dict(sys.modules):
        for name in list(sys.modules):
            if name in {"routes", "services", "prompt_loader"} or name.startswith(("routes.", "services.")):
                del sys.modules[name]
        reviews = load_file("purchase_reviews_fixture", "student-1/backend/app.py")
    reviews.app.template_folder = str(ROOT / "student-1/frontend/templates")
    reviews.AI_MODE_ENABLED = False
    database = load_file("purchase_reviews_database", "student-1/database/app.py")
    database.DB_PATH = str(tmp_path / "reviews.sqlite")
    with sqlite3.connect(database.DB_PATH) as connection:
        connection.executescript((ROOT / "student-1/database/schema.sql").read_text())
    db_client = database.app.test_client()
    state = SimpleNamespace(unavailable=False, malformed=False, calls=[])
    old_post, old_get = requests.post, requests.get

    def post(url, **kwargs):
        if url == reviews.ORDERS_API_URL.rstrip("/") + "/api/orders/verified-purchase":
            state.calls.append(kwargs)
            if state.unavailable:
                raise requests.Timeout("Sensitive transport details must never be logged")
            if state.malformed:
                return SimpleNamespace(status_code=200, json=lambda: {"verified_purchase": "true"})
            return Reply(system.api.post("/api/orders/verified-purchase", json=kwargs["json"], headers=kwargs["headers"]))
        if url.startswith(reviews.DATABASE_URL):
            return Reply(db_client.post(urlsplit(url).path, json=kwargs["json"]))
        return old_post(url, **kwargs)

    def get(url, **kwargs):
        if url.startswith(reviews.DATABASE_URL):
            return Reply(db_client.get(urlsplit(url).path))
        return old_get(url, **kwargs)

    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(requests, "get", get)

    def proof(role="owner", product_id=101):
        result = system.clients[role].post("/api/orders/purchase-proof", headers=ISSUE_HEADERS,
                                          json={"product_id": product_id, "customer_id": 999})
        assert result.status_code == 200
        return result.json["access_token"]

    def submit(token=None, form=False, **overrides):
        payload = {"product_id": 101, "rating": 5, "comment": "Synthetic review", **overrides}
        kwargs = {"data" if form else "json": payload}
        return reviews.app.test_client().post("/reviews/submit-form" if form else "/reviews",
                                              headers={"Authorization": "Bearer " + token} if token else {}, **kwargs)

    def confirm():
        order = create(system)
        assert system.api.put(f"/api/orders/{order}", headers=system.issue("staff"), json={"status": "CONFIRMED"}).status_code == 200
        return order

    return SimpleNamespace(system=system, reviews=reviews, database=database, db=db_client,
                           state=state, proof=proof, submit=submit, confirm=confirm)


@pytest.mark.parametrize("form", [False, True])
def test_confirmed_owner_can_review_through_real_session_orders_and_database(integration, form):
    i = integration
    i.confirm()
    assert i.submit(i.proof(), form=form, is_flagged=1, sentiment_score=-1).status_code == 201
    rows = i.db.get("/reviews/101").json
    assert len(rows) == 1 and rows[0]["customer_id"] == 1
    assert rows[0]["sentiment_score"] == 0 and rows[0]["is_flagged"] == 0
    call = i.state.calls[0]
    assert call["json"] == {"product_id": 101} and call["allow_redirects"] is False
    assert call["timeout"] == 5
    if form:
        assert i.submit(i.proof(), form=True).status_code == 409


@pytest.mark.parametrize("condition", ["pending", "cancelled", "unrelated_product", "other_owner"])
@pytest.mark.parametrize("form", [False, True])
def test_only_confirmed_purchase_for_signed_customer_and_product_allows_review(integration, condition, form):
    i = integration
    order = i.confirm() if condition != "pending" else create(i.system)
    if condition == "cancelled":
        assert i.system.api.delete(f"/api/orders/{order}", headers=i.system.issue("owner")).status_code == 200
    role = "other" if condition == "other_owner" else "owner"
    product = 102 if condition == "unrelated_product" else 101
    assert i.submit(i.proof(role, product), form=form, product_id=product).status_code == 403
    assert i.db.get("/reviews").json == []


@pytest.mark.parametrize("form", [False, True])
def test_client_customer_id_cannot_impersonate_a_confirmed_owner(integration, form):
    i = integration
    i.confirm()
    assert i.submit(i.proof("other"), form=form, customer_id=1).status_code == 403
    assert i.submit(i.proof(), form=form, customer_id=2).status_code == 403
    assert i.submit(i.proof(), form=form, product_id=102).status_code == 403
    assert not i.state.calls and i.db.get("/reviews").json == []


def invalid_proof(i, kind):
    if kind == "missing":
        return None
    if kind == "forged":
        return "invalid-signature"
    if kind == "crud":
        return i.system.issue("owner")["Authorization"].split(" ", 1)[1]
    secret = os.environ["ORDERS_PURCHASE_SECRET"]
    claims = {"iss": "kicklab-shared", "aud": "orders-verified-purchase", "scope": "reviews:purchase",
              "role": "customer", "customer_id": 1, "product_id": 101}
    if kind in {"scope", "aud", "role"}:
        claims[kind] = "incorrect"
    signer = URLSafeTimedSerializer(secret, salt="orders-verified-purchase-v1")
    if kind == "expired":
        with patch("itsdangerous.timed.time.time", return_value=time.time() - 121):
            return signer.dumps(claims)
    return signer.dumps(claims)


@pytest.mark.parametrize("kind", ["missing", "forged", "expired", "crud", "scope", "aud", "role"])
@pytest.mark.parametrize("form", [False, True])
def test_invalid_proof_is_denied_by_both_reviews_submission_routes_and_orders(integration, kind, form):
    i = integration
    i.confirm()
    token = invalid_proof(i, kind)
    result = i.submit(token, form=form)
    assert result.status_code == 401 and result.json["code"] == "unauthorized"
    headers = {"Authorization": "Bearer " + token} if token else {}
    assert i.system.api.post("/api/orders/verified-purchase", json={"product_id": 101}, headers=headers).status_code == 401
    assert not i.state.calls and i.db.get("/reviews").json == []


@pytest.mark.parametrize("mode", ["timeout", "malformed", "database_failure"])
def test_orders_failure_never_creates_review_or_logs_transport_details(integration, monkeypatch, capsys, mode):
    i = integration
    i.confirm()
    if mode == "timeout":
        i.state.unavailable = True
    elif mode == "malformed":
        i.state.malformed = True
    else:
        monkeypatch.setattr(i.system.backend, "db_post", lambda *args: (_ for _ in ()).throw(requests.ConnectionError("private transport")))
    result = i.submit(i.proof())
    assert result.status_code == 503 and result.json["code"] == "unavailable"
    assert i.db.get("/reviews").json == []
    logs = capsys.readouterr()
    assert "transport" not in result.get_data(as_text=True) + logs.out + logs.err


def test_boolean_only_endpoint_cannot_be_used_as_orders_crud_credential(integration):
    i = integration
    i.confirm()
    token = i.proof()
    headers = {"Authorization": "Bearer " + token}
    result = i.system.api.post("/api/orders/verified-purchase", json={"product_id": 101, "customer_id": 2}, headers=headers)
    assert result.json == {"verified_purchase": True}
    assert result.headers["Cache-Control"] == "no-store"
    assert i.system.api.get("/api/orders", headers=headers).status_code == 401
    assert i.system.api.get("/api/orders/1", headers=headers).status_code == 401
    assert i.system.api.post("/api/orders/verified-purchase", json={"product_id": 101}, headers=i.system.issue("staff")).status_code == 401


def test_issuer_is_customer_session_bound_and_cors_restricted(integration):
    i = integration
    client = i.system.clients["owner"]
    result = client.post("/api/orders/purchase-proof", headers=ISSUE_HEADERS, json={"product_id": 101, "customer_id": 2})
    claims = URLSafeTimedSerializer(os.environ["ORDERS_PURCHASE_SECRET"], salt="orders-verified-purchase-v1").loads(result.json["access_token"])
    assert claims["customer_id"] == 1 and claims["product_id"] == 101
    assert result.json["expires_in"] == 120 and result.headers["Cache-Control"] == "no-store"
    assert result.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert result.headers["Access-Control-Allow-Credentials"] == "true"
    assert i.system.clients["staff"].post("/api/orders/purchase-proof", headers=ISSUE_HEADERS, json={"product_id": 101}).status_code == 403
    for headers in ({"Origin": ORIGIN}, {**ISSUE_HEADERS, "Origin": "https://evil.example"}):
        result = client.post("/api/orders/purchase-proof", headers=headers, json={"product_id": 101})
        assert result.status_code == 403
    client.get("/logout")
    assert client.post("/api/orders/purchase-proof", headers=ISSUE_HEADERS, json={"product_id": 101}).status_code == 401


@pytest.mark.parametrize("problem", ["missing", "reused", "cloud_origin"])
def test_misconfigured_proof_flow_fails_closed(integration, monkeypatch, problem):
    i = integration
    token = i.proof()
    if problem == "missing":
        monkeypatch.delenv("ORDERS_PURCHASE_SECRET")
    elif problem == "reused":
        monkeypatch.setenv("ORDERS_PURCHASE_SECRET", os.environ["ORDERS_CRUD_SECRET"])
    else:
        monkeypatch.setenv("APP_ENV", "cloud")
        monkeypatch.delenv("REVIEWS_FRONTEND_ORIGIN", raising=False)
    result = i.system.clients["owner"].post("/api/orders/purchase-proof", headers=ISSUE_HEADERS, json={"product_id": 101})
    assert result.status_code == 503
    if problem != "cloud_origin":
        assert i.submit(token).status_code == 503
        assert i.system.api.post("/api/orders/verified-purchase", headers={"Authorization": "Bearer " + token}, json={"product_id": 101}).status_code == 503
    assert i.db.get("/reviews").json == []


def test_checkout_preserves_existing_catalog_name_and_ui_escapes_it(integration, tmp_path):
    i = integration
    owner = i.system.clients["owner"]
    owner.get("/order/101")
    with owner.session_transaction() as session:
        nonce = session["orders_checkout_csrf"]
    response = owner.post("/order/101/place", data={"quantity": 1, "orders_csrf": nonce}, headers={"Origin": "http://localhost"})
    assert response.status_code == 302
    order_id = int(response.location.rsplit("/", 1)[1])
    detail = i.system.api.get(f"/api/orders/{order_id}", headers=i.system.issue("owner"))
    assert detail.json["items"][0]["product_name"] == "Synthetic shoe"
    for path in ("/", "/admin"):
        assert "${orderItemLabel(item)}" in i.system.frontend.app.test_client().get(path).get_data(as_text=True)
    source = (ROOT / "student-4/frontend/templates/partials/orders_auth.html").read_text()
    helper = source[source.index("        function orderItemLabel"):]
    run_js(tmp_path, helper + '\nif(orderItemLabel({product_name:"<b>&",product_id:1})!=="&lt;b&gt;&amp;")throw Error("unsafe");\nif(orderItemLabel({product_id:1})!=="Product #1")throw Error("fallback"); print("PASS");')


def test_existing_database_migration_retains_orders_and_old_unknown_name(tmp_path):
    init = load_file("purchase_migration_fixture", "student-4/database/init_db.py")
    target = tmp_path / "old.sqlite"
    old_schema = (ROOT / "student-4/database/schema.sql").read_text().replace("    product_name TEXT,\n", "")
    with sqlite3.connect(target) as connection:
        connection.executescript(old_schema)
        connection.execute("INSERT INTO orders(customer_id,total_amount,status) VALUES(1,1,'CONFIRMED')")
        connection.execute("INSERT INTO order_items(order_id,product_id,quantity,unit_price,subtotal) VALUES(1,1,1,1,1)")
    init.initialize(str(target))
    init.initialize(str(target))
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT product_id,product_name FROM order_items").fetchall() == [(1, None)]
        assert connection.execute("SELECT status FROM orders").fetchone() == ("CONFIRMED",)


def run_js(tmp_path, source):
    runtime = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
    if not runtime.exists():
        pytest.skip("JavaScriptCore runtime unavailable; install a browser runner for this check")
    script = tmp_path / "browser.js"
    script.write_text(source)
    result = subprocess.run([str(runtime), str(script)], capture_output=True, text=True, timeout=10, check=False)  # noqa: S603 - fixed local runtime, generated test fixture
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS" in result.stdout


@pytest.mark.parametrize("issuer_ok", [True, False])
def test_rendered_browser_submission_fetches_and_supplies_proof_in_header(integration, tmp_path, issuer_ok):
    response = integration.reviews.app.test_client().get("/submit?product_id=101&customer_id=999")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'name="customer_id"' not in html
    source = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
    prelude = r'''
    let handler, calls=[], destination=null;
    const button={disabled:false}, status={textContent:''};
    const form={addEventListener:(event,fn)=>{handler=fn;},querySelector:()=>button};
    const document={getElementById:id=>id==='reviewForm'?form:status};
    const window={location:{assign:url=>destination=url}};
    const AbortSignal={timeout:()=>({})};
    class FormData {get(key){return {product_id:'101',rating:'5',comment:'Synthetic'}[key];}}
    class URLSearchParams {constructor(fields){this.fields=fields;}}
    const fetch=async(url,options)=>{
      calls.push({url,options});
      return calls.length===1 ? {ok:ISSUER_OK,json:async()=>({access_token:'memory-only-test-proof',error:'Log in'})}
        : {ok:true,json:async()=>({message:'Review submitted.'})};
    };
    '''.replace("ISSUER_OK", json.dumps(issuer_ok))
    assertions = r'''
    handler({preventDefault:()=>{}}).then(()=>{
      if(calls[0].options.credentials!=='include')throw Error('session missing');
      if(JSON.parse(calls[0].options.body).product_id!==101)throw Error('product binding missing');
      if(calls[0].options.headers['X-Reviews-Proof-Request']!=='1')throw Error('CSRF header missing');
      if(ISSUER_OK){
        if(calls.length!==2||calls[1].url!=='/reviews/submit-form')throw Error('submit missing');
        if(calls[1].options.headers.Authorization!=='Bearer memory-only-test-proof')throw Error('proof missing');
        if(calls[1].options.credentials!=='omit'||!destination)throw Error('bad submit');
      }else if(calls.length!==1||destination!==null)throw Error('must fail closed');
      if(button.disabled)throw Error('button stuck');
      print('PASS');
    }).catch(error=>{print(error);throw error;});
    '''.replace("ISSUER_OK", json.dumps(issuer_ok))
    run_js(tmp_path, prelude + source + assertions)
