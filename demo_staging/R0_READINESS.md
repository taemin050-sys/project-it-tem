# IT-TEM Remote Demo R0 — Canonical and Security Gate
- Baseline GitHub dev cfb5bc5f5ba225680f4ab841c3065155ecbc602a, FE PR16 5783287dba12deb571a38996603e1a4641dea9b.
- Preserve W2 GCP Mock at /home/macstudio/ittem-b0-e2e-20261030/; do NOT overwrite.
- Staging-only /demo/api/... endpoints are PROPOSALS; canonical 11 B0 APIs unchanged.
- Cloudflare OTP only outer boundary; use per-evaluator invitation, secure HttpOnly SameSite cookie and database Job ownership for all B0 read/write/asset/download.
- Unauthenticated 401, foreign Job 404; Job IDs are not credentials. Origin checked for unsafe requests.
- Quick Tunnel stays OFF until verified email allowlist and 2-network external OTP tests. No wildcard domain.
- Mock stage timings do not imply actual AI latency. Live OFF. Issues 12–14 remain.
- Operations restricted to 127.0.0.1:18080, one Uvicorn worker, one SQLite writer.
- Config/invite files 0600, NEVER checked into Git, frontend assets, logs.
