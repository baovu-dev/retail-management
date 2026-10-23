"""Opt-in Azure Orders HTTP evidence collection; never deployment or local evidence."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import stat
import time
import uuid

import requests

LIMIT = 65536
COLLECTOR = "orders-cloud-http-v1"
CORE = {
    "frontend": ("GET", "/", 200), "health": ("GET", "/api/health", 200),
    "count": ("GET", "/api/orders/count", 200), "browser_api_access": ("GET", "/api/orders/count", 200),
    "create": ("POST", "/api/orders", 201), "read": ("GET", "/api/orders/{order_id}", 200),
    "update": ("PUT", "/api/orders/{order_id}", 200), "cancel": ("DELETE", "/api/orders/{order_id}", 200),
    "read_after_cancel": ("GET", "/api/orders/{order_id}", 200),
    "ai_disabled": ("POST", "/api/order-assistant", 403), "mcp_disabled": ("POST", "/api/mcp/order-status", 403),
    "rag_disabled": ("POST", "/api/rag/answer", 403), "multi_agent_disabled": ("POST", "/api/multi-agent/workflow", 403),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def positive_id(value):
    return type(value) is int and 0 < value <= 2147483647


def decode_object(raw):
    if len(raw) > LIMIT:
        raise ValueError("Input too large")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON key")
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def read_object(path):
    return decode_object(Path(path).read_bytes())


def validate_config(config):
    domain, commit = config.get("environment_domain"), config.get("commit_sha")
    if (not isinstance(domain, str) or not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+\.azurecontainerapps\.io", domain)
            or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or type(config.get("run_id")) is not int or config["run_id"] <= 0):
        raise ValueError("Invalid deployment identity")
    for key, app in (("frontend_origin", "student4-frontend"), ("api_origin", "student4-backend")):
        if config.get(key) != f"https://{app}.{domain}":
            raise ValueError("Expected exact Azure public app origin")
        image = config.get("images", {}).get(app, "")
        if not isinstance(image, str) or not re.fullmatch(r"[a-z0-9.-]+\.azurecr\.io/student-4:[0-9a-f]{7,40}", image):
            raise ValueError("Commit-tagged deployed image evidence required")
        if not commit.startswith(image.rsplit(":", 1)[1]):
            raise ValueError("Deployed image commit mismatch")
    return config


def deployment_config(path):
    return validate_config(read_object(path))


def credentials(path):
    if stat.S_IMODE(Path(path).stat().st_mode) & 0o077:
        raise ValueError("Credential file must be private (0600)")
    value = read_object(path)
    token_mode = all("bearer_token" in value.get(role, {}) for role in ("owner", "other", "staff"))
    for role in ("owner", "other", "staff"):
        entry = value.get(role, {})
        if token_mode:
            token = entry.get("bearer_token")
            if not isinstance(token, str) or not 16 <= len(token) <= 4096 or re.search(r"\s", token):
                raise ValueError("Missing CRUD credential")
        elif (not isinstance(entry.get("email"), str) or not entry["email"]
              or not isinstance(entry.get("password"), str) or not entry["password"]):
            raise ValueError("Shared-login credentials required")
    key = "bearer_token" if token_mode else "email"
    if (not positive_id(value["owner"].get("customer_id")) or not positive_id(value["other"].get("customer_id"))
            or value["owner"]["customer_id"] == value["other"]["customer_id"]
            or len({value[role][key] for role in ("owner", "other", "staff")}) != 3):
        raise ValueError("Distinct synthetic customer and staff identities required")
    return value


def public_dns(origins):
    for origin in origins:
        host = origin.removeprefix("https://")
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ValueError("Public Azure DNS required")


def browser_count(frontend, api):
    """A real isolated browser fetch, not an HTTP Origin header pretending to be CORS."""
    from playwright.sync_api import sync_playwright
    target = api + "/api/orders/count"
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            context = browser.new_context(service_workers="block")
            # Do not load customer orders, third-party assets, or arbitrary redirects.
            def restrict(route):
                request = route.request
                if request.method == "GET" and request.url in {frontend + "/", target}:
                    route.continue_()
                else:
                    route.abort()
            context.route("**/*", restrict)
            page = context.new_page()
            page.goto(frontend + "/", wait_until="domcontentloaded", timeout=30000)
            result = page.evaluate("""async ({target, api}) => {
                if (typeof API_BASE !== 'string' || API_BASE !== api) return {cors_allowed: false};
                try {
                    const response = await fetch(target, {credentials: 'omit', cache: 'no-store',
                        signal: AbortSignal.timeout(15000)});
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let size = 0, text = '';
                    while (true) {
                        const {done, value} = await reader.read();
                        if (done) break;
                        size += value.length;
                        if (size > 65536) { await reader.cancel(); return {http_status: response.status, cors_allowed: false}; }
                        text += decoder.decode(value, {stream: true});
                    }
                    text += decoder.decode();
                    const data = JSON.parse(text);
                    return {http_status: response.status, count: data.count, cors_allowed: true};
                } catch (_) { return {cors_allowed: false}; }
            }""", {"target": target, "api": api})
            return result
        finally:
            browser.close()


class StopCollection(Exception):
    """Only fixed check identifiers are emitted; never an HTTP exception or body."""


class SessionCredentials:
    """Mint fresh CRUD credentials from real shared-login sessions; never sign tokens here."""
    def __init__(self, config, identities, *, session_factory=requests.Session):
        self.shared = config.get("shared_origin")
        if self.shared != f"https://shared-backend.{config['environment_domain']}":
            raise ValueError("Exact public shared origin required")
        self.frontend, self.identities, self.factory = config["frontend_origin"], identities, session_factory
        self.sessions = {}

    @staticmethod
    def read_json(response):
        raw = bytearray()
        for chunk in response.iter_content(8192):
            raw.extend(chunk)
            if len(raw) > LIMIT:
                raise StopCollection("credential_issuance")
        return decode_object(raw)

    def __call__(self, role):
        identity = self.identities[role]
        public_dns((self.shared,))
        if role not in self.sessions:
            session = self.factory()
            session.trust_env = False
            self.sessions[role] = session
            response = session.post(self.shared + "/login", data={"email": identity["email"], "password": identity["password"]},
                                    timeout=(5, 30), allow_redirects=False, stream=True, verify=True)
            try:
                if response.status_code != 302:
                    raise StopCollection("credential_issuance")
            finally:
                response.close()
        response = self.sessions[role].post(self.shared + "/api/orders/crud-token",
                                          headers={"Origin": self.frontend, "X-Orders-Token-Request": "1"},
                                          timeout=(5, 30), allow_redirects=False, stream=True, verify=True)
        try:
            if response.status_code != 200:
                raise StopCollection("credential_issuance")
            data = self.read_json(response)
            expected = "staff" if role == "staff" else "customer"
            token = data.get("access_token")
            if (data.get("role") != expected or data.get("expires_in") != 120
                    or not isinstance(token, str) or not 16 <= len(token) <= 4096 or re.search(r"\s", token)
                    or expected == "customer" and data.get("customer_id") != identity["customer_id"]):
                raise StopCollection("credential_issuance")
            return token
        finally:
            response.close()

    def close(self):
        for session in self.sessions.values():
            session.close()


class Collector:
    def __init__(self, config, auth, product_id, unit_price, output, *, session=None,
                 browser_probe=browser_count, resolve=public_dns, delay=2, token_provider=None):
        if not positive_id(product_id) or not Decimal("0") < Decimal(str(unit_price)) <= Decimal("10000"):
            raise ValueError("Dedicated test product and positive bounded price required")
        self.config, self.auth = validate_config(config), auth
        self.token_provider = token_provider
        self.front, self.api = config["frontend_origin"], config["api_origin"]
        self.item = {"product_id": product_id, "quantity": 1, "unit_price": float(Decimal(str(unit_price)).quantize(Decimal("0.01")))}
        if self.item["unit_price"] <= 0:
            raise ValueError("Price rounds to zero")
        if not 0 <= delay <= 30:
            raise ValueError("Bounded persistence delay required")
        self.output, self.browser_probe, self.resolve, self.delay = Path(output), browser_probe, resolve, delay
        self.session = session or requests.Session()
        self.session.trust_env = False  # no ambient proxies, netrc authentication or disabled TLS verification
        self.report = {"feature": "student-4", "run_id": config["run_id"], "commit_sha": config["commit_sha"],
                       "timestamp": now(), "profile": "mandatory-ai-disabled", "test_order_id": None,
                       "access": {"kind": "direct-public-backend", "environment_domain": config["environment_domain"],
                                  "frontend_app": "student4-frontend", "api_app": "student4-backend",
                                  "frontend_origin": self.front, "api_origin": self.api},
                       "collector": COLLECTOR, "collection_id": str(uuid.uuid4()), "collection_status": "failed", "checks": {},
                       "retention": "No confirmed test order yet. An unexpected or timed-out POST may require private synthetic-account reconciliation.",
                       "limitations": ["Repeated read proves request-level retention only, not restart/redeployment persistence.",
                                       "Commit identity comes from operator-supplied deployed image configuration, not an HTTP version endpoint.",
                                       "No bonus or human release approval is claimed."]}
        for name, (method, path, _) in CORE.items():
            self.report["checks"][name] = {"method": method, "url": (self.front if name == "frontend" else self.api) + path,
                                          "http_status": None, "passed": False, "timestamp": None, "observed": {}}

    def save(self):
        self.report["timestamp"] = now()
        self.handle.seek(0)
        json.dump(self.report, self.handle, indent=2)
        self.handle.write("\n")
        self.handle.truncate()
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def request(self, name, method, path, *, role=None, payload=None, invalid=False, html=False):
        url = (self.front if name == "frontend" else self.api) + path
        row = {"method": method, "url": url, "http_status": None, "passed": False, "timestamp": now(), "observed": {}}
        self.report["checks"][name] = row
        self.save()  # retain attempted mutations even if the process is interrupted
        headers = {"Cache-Control": "no-cache, no-store", "Connection": "close"}
        if role:
            issued = self.token_provider(role) if self.token_provider else self.auth[role]["bearer_token"]
            headers["Authorization"] = "Bearer " + issued
        if invalid:
            headers["Authorization"] = "Bearer invalid-collector-probe"
        try:
            self.session.cookies.clear()
            response = self.session.request(method, url, json=payload, headers=headers,
                                            timeout=(5, 30), allow_redirects=False, stream=True, verify=True)
            try:
                row["http_status"] = response.status_code
                body = bytearray()
                for chunk in response.iter_content(8192):
                    body.extend(chunk)
                    if len(body) > LIMIT:
                        raise StopCollection(name)
                if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                    raise StopCollection(name)
                if int(response.headers.get("Age", "0")) > 0:
                    raise StopCollection(name)
                if html:
                    if "text/html" not in response.headers.get("Content-Type", "").lower():
                        raise StopCollection(name)
                    return row, body.decode("utf-8")
                if "application/json" not in response.headers.get("Content-Type", "").lower():
                    raise StopCollection(name)
                data = decode_object(body)
                return row, data
            finally:
                response.close()
        except (requests.RequestException, ValueError, TypeError, StopCollection):
            raise StopCollection(name) from None

    def require(self, name, row, passed, observed):
        row["passed"], row["observed"], row["timestamp"] = bool(passed), observed, now()
        self.save()
        if not passed:
            raise StopCollection(name)

    def same_order(self, data, status, *, items=False):
        valid = (type(data.get("order_id")) is int and data["order_id"] == self.report["test_order_id"]
                 and data.get("status") == status)
        if items:
            records = data.get("items")
            valid = (valid and data.get("customer_id") == self.auth["owner"]["customer_id"]
                     and isinstance(records, list) and len(records) == 1 and isinstance(records[0], dict)
                     and all(type(records[0].get(key)) is type(value) and records[0][key] == value for key, value in self.item.items())
                     and type(data.get("total_amount")) in (int, float) and data["total_amount"] == self.item["unit_price"])
        return valid

    def collect(self):
        self.resolve((self.front, self.api))
        row, text = self.request("frontend", "GET", "/", html=True)
        match = re.search(r'const API_BASE\s*=\s*("[^"\n]+")\s*;', text)
        api_base = json.loads(match[1]) if match else None
        rendered = "My Orders" in text and 'id="orderDetail"' in text
        self.require("frontend", row, row["http_status"] == 200 and rendered and api_base == self.api,
                     {"orders_ui_rendered": rendered, "api_base": self.api if api_base == self.api else None})
        for name, path, key in (("health", "/api/health", "database_connected"), ("count", "/api/orders/count", "count")):
            row, data = self.request(name, "GET", path)
            value = data.get(key)
            valid = value is True if name == "health" else type(value) is int and value >= 0
            self.require(name, row, row["http_status"] == 200 and valid, {key: value if valid else None})
        row = self.report["checks"]["browser_api_access"]
        row["timestamp"], row["request_origin"] = now(), self.front
        result = self.browser_probe(self.front, self.api)
        row["http_status"] = result.get("http_status") if type(result.get("http_status")) is int else None
        count = result.get("count")
        valid = row["http_status"] == 200 and result.get("cors_allowed") is True and type(count) is int and count >= 0
        self.require("browser_api_access", row, valid, {"cors_allowed": valid, "count": count if valid else None})
        for name, invalid in (("unauthenticated_create_denied", False), ("invalid_credential_denied", True)):
            row, data = self.request(name, "POST", "/api/orders", payload={}, invalid=invalid)
            denied = row["http_status"] in {401, 403} and data.get("code") in {"unauthorized", "forbidden"}
            self.require(name, row, denied, {"access_denied": denied})
        payload = {"customer_id": self.auth["owner"]["customer_id"], "items": [self.item]}
        row, data = self.request("create", "POST", "/api/orders", role="owner", payload=payload)
        order_id = data.get("order_id")
        if row["http_status"] == 201 and positive_id(order_id):
            self.report["test_order_id"] = order_id
            self.report["retention"] = "Synthetic order retained. Cancellation is a status change; never physically delete records automatically."
            for name, spec in CORE.items():
                if "{order_id}" in spec[1]:
                    self.report["checks"][name]["url"] = self.api + spec[1].replace("{order_id}", str(order_id))
            self.save()
        valid = row["http_status"] == 201 and positive_id(order_id) and data.get("status") == "PENDING"
        self.require("create", row, valid, {"order_id": order_id if positive_id(order_id) else None,
                                           "status": "PENDING" if data.get("status") == "PENDING" else None})
        path = f"/api/orders/{self.report['test_order_id']}"
        row, data = self.request("read", "GET", path, role="owner")
        preserved = self.same_order(data, "PENDING", items=True)
        self.require("read", row, row["http_status"] == 200 and preserved,
                     {"order_id": order_id, "items_preserved": preserved})
        row, data = self.request("ownership_denied", "GET", path, role="other")
        denied = row["http_status"] == 403 and data.get("code") == "forbidden"
        self.require("ownership_denied", row, denied, {"access_denied": denied})
        for name, method, status in (("update", "PUT", "CONFIRMED"), ("cancel", "DELETE", "CANCELLED")):
            row, data = self.request(name, method, path, role="staff", payload={"status": status} if method == "PUT" else None)
            valid = row["http_status"] == 200 and self.same_order(data, status)
            self.require(name, row, valid, {"order_id": order_id, "status": status if valid else None})
        time.sleep(self.delay)
        row, data = self.request("read_after_cancel", "GET", path, role="owner")
        preserved = self.same_order(data, "CANCELLED", items=True)
        self.require("read_after_cancel", row, row["http_status"] == 200 and preserved,
                     {"order_id": order_id, "status": "CANCELLED" if preserved else None, "items_preserved": preserved})
        for name, (_, path, _) in CORE.items():
            if name.endswith("_disabled"):
                row, data = self.request(name, "POST", path, payload={})
                disabled = row["http_status"] == 403 and data.get("code") == "disabled"
                self.require(name, row, disabled, {"code": "disabled" if disabled else None})
        self.report["collection_status"] = "complete"

    def run(self):
        # Reserve before network access; never overwrite a prior collection.
        descriptor = os.open(self.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as self.handle:
            self.save()
            try:
                self.collect()
            except Exception:
                # Network/browser/configuration exceptions may carry bearer tokens or bodies.
                self.report["collection_status"] = "failed"
            finally:
                self.save()
                self.session.close()
        return self.report["collection_status"] == "complete"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-file", required=True, type=Path)
    parser.add_argument("--credentials-file", required=True, type=Path)
    parser.add_argument("--product-id", required=True, type=int)
    parser.add_argument("--unit-price", required=True, type=Decimal)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-test-order", action="store_true", help="Explicitly permit one synthetic cloud order and status changes")
    args = parser.parse_args()
    if not args.allow_test_order:
        parser.error("--allow-test-order is required for an authorized real collection")
    try:
        config, auth = deployment_config(args.deployment_file), credentials(args.credentials_file)
        provider = None if "bearer_token" in auth["owner"] else SessionCredentials(config, auth)
        try:
            collector = Collector(config, auth, args.product_id, args.unit_price, args.output, token_provider=provider)
            collector.report["deployment_config_sha256"] = hashlib.sha256(args.deployment_file.read_bytes()).hexdigest()
            passed = collector.run()
        finally:
            if provider:
                provider.close()
    except Exception:
        print("Collection failed: invalid configuration or output unavailable; no exception details emitted.")
        return 1
    print("Orders cloud collection: " + ("complete; human review still required" if passed else "failed/incomplete; inspect the private evidence file"))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
