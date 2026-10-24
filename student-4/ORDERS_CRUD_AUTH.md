# Orders CRUD authentication contract

All environments enforce the same bearer contract. There is no local or cloud
authentication bypass. This implementation has not been deployed or collected
against Azure. Local integration tests use actual Flask/session/signature/SQLite
logic with upstream transports confined to test clients.

## Session issuer and scopes

`POST /api/orders/crud-token` on shared login requires its authenticated session
cookie, exact `Origin: ORDERS_FRONTEND_ORIGIN` and `X-Orders-Token-Request: 1`.
The cross-origin preflight allows only that configured frontend and credentials.
Identity always comes from the server's session, never request JSON or a URL.
Responses contain `access_token`, `expires_in: 120`, `role`, and the signed-in
customer's `customer_id` (null for staff), with `Cache-Control: no-store`.
The shared issuer needs a private session key of at least 32 characters and a
private staff password for staff issuance. Logout stops new issuance; already
issued bearer credentials remain usable until their 120-second expiry.

Tokens use a separate `ORDERS_CRUD_SECRET` (at least 32 characters, different
from `ORDERS_MCP_SECRET`), signing salt `orders-crud-v1`, issuer `kicklab-shared`,
audience `orders-crud`, and exactly one role-specific scope:

| Role | Scope | Signed identity |
| --- | --- | --- |
| customer | `orders:customer:crud` | `customer_id`, a positive integer |
| staff | `orders:staff:manage` | `staff_email`, from the staff session |

MCP and Multi-Agent credentials cannot authorize CRUD; CRUD tokens cannot be
used for those modes. Client-supplied roles, customer IDs and staff emails never
create authority. The collector does not need any signing or Flask session key.

## API permissions

Send `Authorization: Bearer <access_token>` to the public Orders backend.

| Endpoint | Customer | Staff |
| --- | --- | --- |
| GET `/api/orders` | Always filtered to signed customer ID | All orders |
| GET `/api/orders?customer_id=N` | Only own ID; other IDs forbidden | May filter by positive ID |
| GET `/api/orders/N` | Own order only | Any order |
| POST `/api/orders` | Create for signed identity; optional `customer_id` must match | Forbidden |
| PUT `/api/orders/N` | Forbidden | Confirm or cancel; cancelled orders cannot reopen |
| DELETE `/api/orders/N` | Cancel own PENDING/CONFIRMED order | Cancel any order |
| POST `/api/order-assistant` | Own order only when AI enabled | Any order when enabled |

Creation accepts `items` containing numeric positive product IDs/quantities and
finite nonnegative prices. Identity and non-item fields are stripped before the
database call. Cancellation retains the record and items and performs no refund.
Repeated cancellation is idempotent. Public `/api/health` and aggregate
`/api/orders/count` deliberately remain available for readiness and the public
Multi-Agent evidence provider; they return no customer/order records. Disabled
AI, MCP, RAG and Multi-Agent keep their existing 403/`disabled` contracts.

Unauthenticated, forged, expired, wrong-audience and wrong-scope requests return
401/`unauthorized` before database access or input validation. A valid identity
lacking ownership or staff permission receives 403/`forbidden`. Missing/weak
secrets or invalid cloud origin settings return 503/`unavailable`, not public
access. Invalid input is 400/`invalid_input`; missing orders are 404/`not_found`;
reopening cancellation is 409/`invalid_transition`.

## UI, checkout and CORS

Both Orders pages obtain a new capability for every protected request and verify
its role matches the page. Credentials are held only in memory; no localStorage,
URLs or persisted browser tokens. API requests omit cookies and carry bearer
authorization. The API permits only the configured Orders frontend origin and
Authorization/Content-Type headers; it does not accept credentialed wildcard CORS.
My Orders no longer uses a client URL customer ID to choose the owner.

Shared checkout signs the same customer capability server-side and sends it
when creating or showing the resulting order. The checkout form includes a
session CSRF nonce; placing an order requires the nonce and the shared page's
same Origin. Server checkout never forwards a browser-supplied identity or staff
credential. Shared token issuance separately requires its explicit origin/header.

Cloud shared sessions use host-only Secure, HttpOnly, SameSite=None cookies for
the existing cross-origin layout. Local sessions use HttpOnly, SameSite=Lax.
Verify the actual cloud browser/cookie policy before claiming a working deployment;
browser restrictions on cross-site cookies may require a team-owned same-site
domain or gateway arrangement. No cloud browser result is claimed here.

## Configuration and deployment preparation

Set the same private `ORDERS_CRUD_SECRET` in shared login and Orders backend,
alongside the existing private `SECRET_KEY`. Compose now passes the CRUD key to
both. The local origin remains `http://localhost:3004`. An absent private key
blocks CRUD rather than preserving the old unauthenticated API.

Azure rendering sets `APP_ENV=cloud`, the exact HTTPS Orders frontend origin in
shared and backend, and references a Container Apps `orders-crud-secret` in both.
The deployment script requires the key explicitly; the workflow references the
new GitHub Actions secret `ORDERS_CRUD_SECRET`. Do not add it to public frontend
settings, report files or command-line arguments. The database retains internal
ingress and receives no CRUD signing key. This code change does not create secrets,
modify resources, run deployment, or bypass the Student 2/3 validation gate.

## Collector and team interface impact

The cloud collector can use three fresh, explicitly issued CRUD bearer credentials
in its existing private file. They expire after 120 seconds; it fails on expiry
without retrying a mutation. Preferred mode is a mode-0600 private file containing
`owner.email`, `owner.password`, `owner.customer_id`, equivalent `other` fields,
and `staff.email`, `staff.password`. Add the exact public `shared_origin` to the
operator-verified deployment config. The collector logs into shared login and
mints a fresh capability per protected operation, verifies the issuer's returned
role/customer ID, and never persists the returned tokens. Anonymous and forged
create probes must be denied before any authenticated create is attempted.

Student 1 Reviews now uses a separate product-bound shared-session proof and the
boolean-only Orders purchase endpoint. It receives no Orders CRUD/staff key.
See [VERIFIED_PURCHASE.md](VERIFIED_PURCHASE.md) for the browser/API contract,
purpose-key provisioning and rollout requirements. Other historical anonymous
CRUD consumers/scripts still require a real shared-session capability.
Count-only integrations remain compatible.

The group must coordinate key provisioning, the Reviews integration, the actual
cloud origins/cookie policy, collector test accounts/product/price, evidence-run
timing and retained cancelled test orders. No group-wide integration, cloud CRUD,
restart persistence or bonus completion follows from passing local tests.
