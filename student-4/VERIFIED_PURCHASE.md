# Reviews / Orders verified purchase contract

This integration is implemented and tested locally; it has not been deployed or
verified on Azure. It does not establish any cloud or AI bonus claim.

## Browser and service contract

Reviews serves its own HTML on Student 1's backend origin, separate from shared
login. A hidden customer ID cannot authenticate that browser. The rendered review
form now obtains a fresh product-bound proof from the shared authenticated session
and sends it to Reviews in a bearer header. No proof is rendered into HTML, placed
in a URL, persisted in storage, or sent to the sentiment model.

1. Shared `POST /api/orders/purchase-proof` requires the shared customer session,
   exact `Origin: REVIEWS_FRONTEND_ORIGIN`, `X-Reviews-Proof-Request: 1`, and JSON
   `{"product_id": 101}`. Customer identity comes exclusively from the session;
   body identity/role fields do not influence it. Staff sessions are forbidden.
   Returns `{"access_token": "...", "expires_in": 120}` with `no-store`.
2. Reviews `POST /reviews` (JSON) and `POST /reviews/submit-form` (form encoded)
   require `Authorization: Bearer <proof>` and product ID, rating 1–5, optional
   comment up to 3000 characters. There is no customer ID form field. Legacy body
   `customer_id`, if supplied, must match the signed identity; it never selects
   the author. Sentiment and flag values are computed server-side.
3. Reviews validates the proof and calls Orders `POST /api/orders/verified-purchase`
   with the same bearer header and **only** JSON `{"product_id": 101}`. No order
   lists/details or staff/CRUD credentials are available to this integration.
4. Orders validates the proof independently and queries its internal database
   using the signed customer ID and product ID. Its public response contains only
   `{"verified_purchase": true}` or `{"verified_purchase": false}`. True requires
   an existing order with status exactly `CONFIRMED` containing that product.
   Pending/cancelled orders, other products and other customers return false.
5. Reviews writes using the signed customer ID only after a true result. Missing,
   forged, expired, wrong audience/scope/role proofs return 401/`unauthorized`;
   a different product/author or no confirmed purchase returns 403/`forbidden`.
   Configuration/upstream failures return 503/`unavailable`, never permission to
   submit. Input errors return 400; duplicate form submission returns 409.

Proofs use `itsdangerous` timed signatures (120 seconds), issuer `kicklab-shared`,
audience `orders-verified-purchase`, scope `reviews:purchase`, role `customer`,
signed positive integer customer/product IDs and salt `orders-verified-purchase-v1`.
These are bearer credentials: protect HTTPS and the shared session. Logout stops
new issuance; existing proofs expire within 120 seconds. A later purchase query
rechecks the current order status, rather than trusting the proof as a purchase.

## Team configuration

Provision the same private, independent `ORDERS_PURCHASE_SECRET` (at least 32
characters, different from CRUD/MCP keys) in **shared, Orders backend and Reviews
backend**. Do not put it in frontend settings, URLs, reports, Git or shell history.
Reviews receives only this purpose-specific key, never the Orders CRUD/MCP keys.
As a purpose-key holder Reviews is trusted to verify/sign purchase-only proofs;
compromise of that service cannot authorize Orders CRUD. Two identical small
verification modules keep the separately built service images self-contained.

Shared also needs its existing private `SECRET_KEY` and
`REVIEWS_FRONTEND_ORIGIN` set to the exact Reviews origin (local default
`http://localhost:5001`; explicit HTTPS required in cloud). Reviews needs
`SHARED_URL` set to the browser-visible shared login origin and `ORDERS_API_URL`
set to the Orders backend origin (HTTPS required with `APP_ENV=cloud`). Root
Compose wires the backend-to-backend Orders address; standalone Student 1 Compose
uses the existing host Docker address unless overridden. The Azure renderer wires
all three key references and HTTPS origins; the deployment workflow/script require
the new private secret. No Azure resources or secrets were changed by this task.

The issuer allows credentialed CORS only for the Reviews origin; the custom header
forces preflight. Reviews submits to its own origin. Cloud shared cookies retain
the existing Secure/HttpOnly/SameSite=None design; local cookies use Lax. Test the
real browser's third-party cookie policy with the team before a cloud run. A
blocked shared cookie fails issuance; use a team-controlled same-site domain or
proxy if required. The Orders database must retain internal ingress. Its internal
query endpoint accepts IDs from the trusted Orders backend, not public callers.
Coordinate rollout of shared + Reviews + Orders together and provision keys before
restarting. Missing configuration intentionally blocks review submission.

## Product names and scope

Shared checkout already fetches the actual catalog product. It now forwards that
name as an optional bounded display snapshot (`product_name`, 1–120 characters)
into the order item. The database migration adds a nullable column without
replacing orders. Customer/staff Orders detail pages escape the snapshot before
HTML insertion. Names provided by direct CRUD clients remain untrusted display
text and never establish product identity or purchase authority. Existing items
with no name keep `Product #ID`; no speculative ID mapping or new catalog API is
used to relabel historical orders.

Historical Reviews edit/delete/moderation and optional MCP/RAG/Multi-Agent routes
are unchanged; this change secures creation and its purchase verification only.
Those legacy routes are not certified as secure by these tests. Other anonymous
Orders CRUD consumers still need their own authenticated integration. Local
transport and JavaScript mocks are not Azure/browser deployment evidence.
