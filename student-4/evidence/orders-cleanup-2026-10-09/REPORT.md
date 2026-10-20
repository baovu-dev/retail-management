# Release 1 cleanup validation — 2026-10-09

Baseline: `7e25183` on `taehyoun/release1-orders`. These checks cover the cleanup
working tree; this directory is introduced by the documentation/evidence commit.
No Release 2 feature was implemented.

## Changes and repository review

The baseline inventory covered all 355 tracked files. Runtime code, tests, CI,
Docker files, prompts, public RAG knowledge and team evidence under `docs/` were
retained. [96 repeated experiment files](archived-files.json), totaling 6,247,409
bytes, were removed after exporting the baseline source and Git history. A durable
external archive was recreated from `7e25183` after the original temporary archive
was lost on host restart. Git history also retains every removed file.

Current runbooks and historical summary pages are in English. The three remaining
files containing Korean are intentional multilingual inputs or unchanged original
review evidence. Compatibility script wrappers remain because historical commands
reference them. Retained raw evidence was compared byte-for-byte with the baseline.
All current Markdown links and Python syntax checks passed.

Orders keeps the shared KICKLAB desktop visual style; the mobile menu toggle and
its JavaScript were removed. [Customer screenshot](orders-desktop.png) and
[staff screenshot](orders-staff.png) were captured in real Chrome with test orders.

Orders startup now creates missing schema only. Named-volume storage preserves
orders across container recreation. Demo seeding refuses existing orders unless
explicitly invoked with `--seed-demo --reset`. Existing installations must import
their old container database before switching to the new volume.

Root Compose now starts shared login with internal API addresses, initializes a
fresh Products DB when absent, and gives the Chatbot browser a host-accessible
API address. The Orders workflow also builds the shared login image.

## Executed checks

| Check | Result |
| --- | --- |
| [Host regression](regression.log), Python 3.13 | 161 passed, 1 optional live test skipped |
| [Container regression](ci-python311.log), Python 3.11 | 161 passed, 1 optional live test skipped |
| [Opt-in real MCP transport test](mcp-live.log) | 1 passed; 5 upstream SDK deprecation warnings |
| [Default Orders image HTTP integration](image-integration.json) | 13 passed |
| Root and standalone Compose config | Both passed |
| All team service images | Built and started in an isolated Compose project |
| Shared login → Products → Orders browser flow | Registration, three store-created orders, customer filtering, detail modal, cancellation and preserved items passed |
| Staff flow | Shared staff login, Orders navigation, confirmation and details passed |
| Desktop layout | No horizontal overflow at 1280px or 1440px; visual comparison with shared home |
| Live AI/MCP/RAG browser calls | Actual Ollama answer, scoped MCP status, RAG supported-status answer and undocumented-delivery abstention passed |
| Database container recreation | Exact order and item records preserved in the new named volume |
| Original local databases | Hashes unchanged; see count in [checks](checks.json) |
| [Saved final RAG review replay](saved-review.log) | Passed against retained evidence digest; no new generation |

Detailed sanitized results and actual AI responses are in [checks.json](checks.json).
No private credentials, cookies, databases or vector indexes were added to Git.

The first staff automation dismissed the browser confirmation dialog; the corrected
staff-only check accepted it and passed. That was a test-driver issue, not a change
to application confirmation behavior. Historical failures remain unchanged.

## Limits and next phase

This was a fresh, isolated local project, with Reviews/Products backend host ports
remapped to 15001/15002 because unrelated existing services occupied 5001/5002.
Shared-to-service traffic still used the real Compose network. Other students'
complete UI/AI acceptance was not performed. Their Reviews/Customers seed startup
behavior remains a team follow-up; this patch changes Orders data lifecycle only.

Two RAG smoke questions were executed live; the original final nine-question
coverage is retained separately rather than claimed as a new run. The logs above
are local checks. Remote CI status belongs to the cleanup PR.

Before Release 2 implementation: review/merge this Release 1 cleanup, confirm the
team's shared startup and persistence expectations, then agree on the common
Multi-Agent interface, human-review flow, two Orders endpoint tests and cloud
platform. Release 2 work should be planned separately from this cleanup.
