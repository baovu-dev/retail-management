# KICKLAB Cloud Deployment Report

- Platform: Azure Container Apps
- Environment domain: kindsky-69b6e6f7.australiaeast.azurecontainerapps.io
- Image tag (commit): 70c78ea
- Timestamp: 2026-10-18T07:00:50Z

## 1. Public apps respond

| App | URL | HTTP | Result |
|---|---|---|---|
| shared-backend | https://shared-backend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |
| student1-backend | https://student1-backend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |
| student2-frontend | https://student2-frontend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |
| student3-backend | https://student3-backend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |
| student4-backend | https://student4-backend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 404 | PASS |
| student4-frontend | https://student4-frontend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |
| student5-backend | https://student5-backend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 404 | PASS |
| student5-frontend | https://student5-frontend.kindsky-69b6e6f7.australiaeast.azurecontainerapps.io | 200 | PASS |

## 2. Integration and cloud baseline

| Check | Expected | Actual | Result |
|---|---|---|---|
| Reviews backend -> internal database (/reviews/stats) | JSON with total_reviews | `{"average_rating":3.5,"flagged_count":1,"total_reviews":11}` | PASS |
| AI-Mode disabled (review summary) | "AI features are disabled" | see Result | PASS |
| MCP disabled (/mcp/rating-summary) | 403 | 403 | PASS |
| RAG disabled (/rag/answer) | 403 | 403 | PASS |
| Multi-Agent disabled (/multi-agent/workflow) | 403 | 403 | PASS |

## 3. Internal-only apps (not reachable from the internet)

| App | External ingress | Result |
|---|---|---|
| student1-database | false | PASS |
| student2-database | false | PASS |
| student2-backend | false | PASS |
| student3-database | false | PASS |
| student4-database | false | PASS |
| student5-database | false | PASS |

## Overall: PASS

Human release decision: Approve by Bao Vu at 2026-10-24T13:37:54+00:00; reason: All six checks passed and the live Reviews data matches the deployment report
