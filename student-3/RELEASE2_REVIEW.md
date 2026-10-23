# Customer Multi-Agent review

The Student 3 workflow reviews only the total customer count and counts by account status. The evidence provider reads the internal Customer database API, discards personal fields before creating agent records, and rejects unrecognized statuses. The server ignores browser-supplied questions and sends a fixed aggregate-only question to the agents. Existing Customer CRUD APIs are a separate concern.

Staff sign in through the shared application. The Student 3 browser fetches a 120-second capability from `/api/customers/review-token` with its shared login cookie. The issuer checks the configured Customer frontend origin and the staff session. Student 3 verifies the token before starting, reading or deciding a workflow. The Multi-Agent server verifies it again for Student 3 workflow access. The reviewer name comes from the signed staff identity, not the form body. The Customer frontend's shared URL must be the public shared-app origin; `SHARED_URL` already supplies this in local Compose and Azure.

Local development requires one distinct random `CUSTOMERS_REVIEW_SECRET` (at least 32 characters) in the shared app, Student 3 backend and local Multi-Agent server environments. Use a privately configured `STAFF_PASSWORD` and `SECRET_KEY` in the shared app. Azure deployment requires `CUSTOMERS_REVIEW_SECRET` as an environment variable; the deploy script puts it into Container Apps secret references for shared and Student 3. The mandatory cloud profile still disables AI services, so a cloud Multi-Agent run is not claimed by this change.

Run `python -m pytest student-3/tests/test_customer_multi_agent_security.py -q` for aggregate and authorization checks. The post-commit endpoint gate separately runs against live Customer backend endpoints.
