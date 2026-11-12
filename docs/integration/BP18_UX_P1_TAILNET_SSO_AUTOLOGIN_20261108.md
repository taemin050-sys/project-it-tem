# BP18 UX-P1 — A/B Tailnet SSO Auto-login

## Before
Existing 8443 Tailnet SSO has verified Tailscale identity; A 10443 / B 10500 separately used invite-code cookies and showed a remote demo login.

## After (A/B isolated candidates)
- Each Tailnet Serve HTTPS port goes through its **own Mac loopback gateway**: 10443 -> 19097 -> SSH tunnel 19096 -> GCP A18096; 10500 -> 19101 -> SSH tunnel 19100 -> GCP B18100.
- Original 8443 -> 18987 and 10000 gateway remain unchanged. No Funnel/public port.
- Gateway strips untrusted Tailnet and x-ittem signed headers before injecting a *new* HMAC-SHA256 assertion for every request, binding Actor, role, method, exact path+query, Host:port, time, nonce.
- HMAC key and backend Actor allowlist are **track-specific**, outside Git and Releases, mode0600 in mode0700 config. Only five already-approved 8443 user accounts become five distinct A/B Actor IDs.
- GCP SSO-only mode `IT_TEM_TAILNET_AUTH_ENABLED=YES`, `IT_TEM_TAILNET_SSO_ONLY=YES`, `IT_TEM_TAILNET_EXPECTED_HOST=...:10443|10500` rejects invalid/unsigned assertions, mismatched host and cookies, does not permit invite code POST.
- FE built with `VITE_IT_TEM_SSO_ONLY=YES` uses the existing `GET /demo/api/session` session probe. Verified team users see the actual `<App />` homepage without invitation form. Unapproved access is denied by gateway, FE does not offer fallback login.
- Track actor, Job DB, Queue, upload and Artifact remain independent, and `LIVE_ENABLED=NO`, `LIVE_EXECUTION_APPROVED=NO`, `WEB_QUEUE=NO`, Fixture OFF. Existing completed jobs and receipts are immutable.

## Validation
- Unit tests signed SSO, Host:port and separate key, unsigned header spoof, invitation-cookie fallback, admin authorization and fail-closed startup.
- Actual Mac Gateways must run as independent launchd agents, not under old 8443 process.
- GCP A/B independently pin release SHA/FE asset SHA and SSO-only auth/config.
- Verify on HTTPS in real Chrome: exact Actor/Role without invite, product homepage, cross-track 401, foreign actor Job404, spoof403/401, CSRF403, QA fixture denied, HTTPS mobile 360/390 login.
- Keep original Live18088, QA18095 and 8443 SHA/Health and previous completed Artifacts unchanged.

## Important operational limitations
- Authenticated 8443 team allowlist and SSO claim rely on Tailscale Serve's injection/stripping of Tailscale identity header, as in the already verified 8443 gateway. A local user with privileged access to the Mac loopback gateway or HMAC keys is outside the remote Tailnet threat boundary.
- Prior A/B invitation tokens are not used in SSO-only mode; do not delete past ledger data before PM-approved retention.
- Existing 8443 registration is the allowlist SSOT; changes must go through an authorized admin.
- The React '실모델 Worker 비활성' labeling is intentional: SSO does not enable paid AI E2E.
- Older fallback releases without SSO_ONLY enforcement are *not* equivalent in security semantics. On rollback, verify the gateway remains active and do not expose the raw tunnel directly to Tailnet.

## Release constraints
A/B historical deployments and prior SHA are separately preserved. Official GitHub dev, Owner PR, protected Live 18088/QA and old 8443 paths unchanged. B final product acceptance 0/38 until six actual paid model cases and Owner/PM approvals.
