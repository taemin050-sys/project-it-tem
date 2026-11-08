# BP18 B5-P1-02 — SSO-Aware Rollback Guard

## Background
The protected B Tailnet HTTPS endpoint at :10500 now requires signed SSO_ONLY. Old
4ae7bf38 is Epoch-compatible but not auth-compatible and MUST NOT be a rollback target.

## Mandatory gate — fixed runtime contract
GCP B config/bp18_required_auth_contract.json (0600, outside Git) contains
version=1, required_mode=TAILNET_SSO_ONLY, exact Tailnet Host:10500 and
verified_sources keyed by immutable release HEAD, each with SHA256 of:
- demo_staging/app.py
- demo_staging/tailnet_assertion.py
- scripts/tailnet_sso_gateway.py
- app/src/demo/DemoGate.tsx

The guard requires this file on the fixed B production root, enforces a
per-release explicit reviewed SHA record and actual content SHA. The relevant
auth hooks must be present. The systemd ExecStartPre on real port18100 also
checks IT_TEM_TAILNET_AUTH_ENABLED=YES, TAILNET_SSO_ONLY=YES and pinned Host.
The official release-control operator calls THE SAME guard for BOTH candidate
AND fallback before stopping B. A denied candidate must leave current B intact.

Pre-SSO releases remain in the prior Epoch allowlist for historical evidence,
but are not in the new SSO compatible runtime list. Never remove/mutate old
release files, DBs, attempts, receipts or historical logs to enforce this policy.

## Required nonbillable validation
1. 6977cd80 current compatible release: PASS, Epoch=1.
2. 4ae7bf38 pre-SSO, though Epoch-allowed: FAIL before stop, exit78.
3. 564e3731 pre-Epoch: FAIL before stop, exit78.
4. New explicitly verified release: PASS. Missing/malformed auth manifest,
   stale source hashes, disabled SSO_ONLY service env: FAIL CLOSED.
5. Cloned DB/symlink prestart + release-control success and refusal scenarios.
6. Existing original GCP A/QA/Live and completed immutable Artifacts unchanged.

## Operational limitations
This is a mandatory systemd/operator gate, not an immutable execution policy
against privileged operators who can replace units, config or launch uvicorn
directly. Auth manifest is separately operator-maintained and must be updated
only after source review and before any candidate release promotion. Do not
automatically trust every Epoch-compatible future SHA. Keys remain private
and are never exported into the source repository or audit packages.

Track A has a distinct isolated deployment path and MUST NOT use this B-only
policy Epoch/rollback operator. An A rollback of SSO source must independently
retain Tailnet signed SSO_ONLY, as verified by a separate A-specific control.
