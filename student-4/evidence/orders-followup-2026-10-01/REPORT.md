# Orders Release 1 follow-up — 2026-10-01 Australia/Sydney

Local branch `taehyoun/release1-orders`, HEAD `6519476`, uncommitted work preserved.
This is **not a completed Release 1** and not a GitHub Actions run.

## Findings and actual changes

No applicable AGENTS.md or original assessment PDF/detail attachment was found.
Current explicit user instructions and the historical plan were used. Runtime in
`/private/tmp/orders-mcp-browser-validation` and its venv/keys/accounts/index/DB
copies were missing after host restart. Existing stopped validation containers
were not restarted with missing bind mounts; no old runtime was regenerated.

RAG root cause: relevant chunks were sufficient to enter free-text generation;
only a response starting with `Insufficient context` abstained. Other responses,
including context lists explaining missing delivery/refund details, became success.
No-reference responses fell back to all relevant citations; confidence measured
retrieval similarity. Historical full responses/grounds confirm this mismatch.

Orders now uses one structured model call for answerability and verbatim evidence,
with strict ref/quote validation. False means insufficient_context; malformed
model output/transport failure stays error. The output is assembled from validated
excerpts. No keyword blacklist, exact-question mapping, new shipping/refund feature,
second RAG service or multi-agent architecture was introduced. Student 1's existing
generation branch, corpus and three agentic mode files remain unchanged.

New offline tests cover related-but-insufficient evidence, documented negative
answers, malformed decisions, fabricated quotations, bad references, model outage,
irrelevant retrieval and Student 1 dispatch. New public-only browser collector is
implemented using root Compose's Orders subset and an isolated host RAG index.
It preserves first-run responses/grounds/model JSON/screenshots and requires review.

Canonical runbooks/report/demo/GitHub drafts now live in
[docs/release-1/student-4](../../../docs/release-1/student-4/README.md).
Old runbook links forward there; feature scripts/imports remain in place. Existing
student-4-ci.yml convention retained; workflow filters cover docs/scripts and root
Compose quiet validation was added. Historical evidence files were not edited.

## New checks actually executed

| Check | Result / evidence |
|---|---|
| Python 3.11 Linux regression with AI/MCP/RAG=false | **140 passed / 1 skipped**, [raw log](ci-python311.log); opt-in live MCP skipped |
| Host Python 3.12 environment | Installed test/RAG/Playwright deps; pip check reports no broken requirements; [versions](host-packages.txt) |
| Root and Student 4 Compose | Both `config --quiet` exit 0; no expanded secrets printed |
| Existing image vs current sources | 19 code/requirements files match, no mismatches; [result](image-source-check.json) |
| Original data preservation | 3 local DBs + 2 stopped-container DBs: **5/5 unchanged**, [result](preservation-results.json) |
| Historical review integrity | Saved same observations still **3 PASS / 2 FAIL**, [result](historical-review-check.json); no model call |
| Remote fetch | origin/main `8e625c2`; remote file changes do not intersect current changed paths; no merge attempted |
| New entry points/docs/homepage | Syntax + collector import passed; 64 local Markdown links valid; actual shared homepage rendered with synthetic session and five expected navigation links; [results](static-checks.json). Destinations not followed live. |
| Share candidates | No private DB/runtime paths or credential-pattern matches; heuristic limitations in [scan](sharing-check.json) |
| Whitespace | `git diff --check` exit 0 |

Regression command:

```sh
docker run --rm -v /Users/ashley/Desktop/retail-management:/repo:ro \
  -w /repo/student-4 -e AI_ENABLED=false -e MCP_ENABLED=false -e RAG_ENABLED=false \
  -e PYTHONDONTWRITEBYTECODE=1 student4-orders:release1-local sh -c \
  'python -m pip install -r tests/requirements.txt > /tmp/pip.log 2>&1 && python -m pip check && python -m pytest tests/ -q -p no:cacheprovider'
```

No Docker rebuild was necessary: Dockerfile/copied inputs match the prior image.
The earlier image report described ARM64, but current inspected image reports
**amd64**, with the same saved image ID. This follow-up records current evidence
instead of repeating the historical architecture claim. Full image integration
13 PASS belongs to the earlier run and was not repeated.

## Attempts and unexecuted checks

- First host dependency install hit sandbox DNS restrictions; retry with permission
  reached PyPI, then cryptography source build failed due missing OpenSSL/pkg-config.
- An ARM64 interpreter attempt was rejected by the Intel host (`Unknown architecture`).
  No ARM64 environment was created. The working host is Python 3.12.10 x86_64.
- Intel-compatible `cryptography<47` prebuilt installation succeeded; the condition
  is recorded in `student-4/scripts/host-constraints.txt`. CI remains Python 3.11.
- Live root-Compose/RAG/Chrome collector command was **rejected at execution approval**.
  It did not start. No new model response, browser screenshot, root runtime success
  or semantic PASS exists. This was not reported as an automatic-review rejection
  because the tool only returned `rejected by user`, without an automatic-review reason.
- The planned model is `llama3.1:8b` (installed digest
  `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e`), seed 42,
  temperature 0, num_predict 384; embedding `nomic-embed-text` digest
  `0a109f422b47e3a30ba2b10eca18548e944e8a23073ee3f3e947efcf3c45e59f`.
  Model selection was fixed before attempted capture. No retry selection occurred.
- New live Student 1 cases, authenticated MCP browser/agentic runs, all-five-feature
  root stack, remote CI, video and Canvas submission are **not run**.

The new live matrix is in `rag_followup.py`: three supported questions, two original
related unknowns, two paraphrases, supported related-topic questions, Korean
implementation/delay contrast and real server outage UI. It is a pending acceptance
matrix, not evidence that any of these new model responses pass.

## Historical evidence retained

- [MCP browser 23 PASS](../orders-mcp-2026-09-30/REPORT.md)
- [RAG browser 11 PASS, limited question coverage](../orders-rag-2026-09-30/REPORT.md)
- [MCP agentic 6 PASS, RAG claims 3 PASS / 2 FAIL, prior CI/image checks](../orders-agentic-ci-2026-09-30/REPORT.md)

No old FAIL was deleted or relabeled. Claim-review thresholds were not weakened.
Original data contents, tokens, credentials and private indexes were not added to
the repository. Follow-up source review and remaining handoff are documented in
[GitHub preparation](../../../docs/release-1/student-4/GITHUB_PREPARATION.md) and
[team blockers](../../../docs/release-1/student-4/TEAM_INTEGRATION.md).
