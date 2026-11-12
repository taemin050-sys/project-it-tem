# B Signed GET burst connection resets — 2026-11-12

Scope: B-only Mac gateway on loopback19101 behind existing Tailnet HTTPS10500. GCP B remains af6f9c37345ac8d3eab7f982fb111384992a3892. No backend, paid/Derived Worker, shared SSH7038, A/Live/QA service, credential or Actor policy change.

## Root cause and evidence

Browser HTTP/2 font/API fan-out produced empty502s (Date + Content-Length0, no gateway JSON/server/auth-path). The Tailscale daemon simultaneously reported `http: proxy error: dial tcp 127.0.0.1:19101: connect: connection reset by peer`. Requests failed while connecting to the Mac listener, before a gateway handler or GCP request. The actual kernel listener showed0/0/5. The running Python3.12 ThreadingHTTPServer had inherited its default pending-accept backlog5. The burst was exhausting that queue; isolated/direct GETs generally succeeded and did not reproduce the browser connection burst.

Changed only the server class used at startup to GatewayHTTPServer(request_queue_size128), matching existing Mac SOMAXCONN128. Runtime now shows0/0/128. Gateway authentication/forwarding class AST is byte-for-byte structurally identical. No request replay or automatic paid retry was introduced. Existing buffered-response/client-abort fix remains separate; it did not fix this dial-before-handler failure.

B gateway drained existing connections and restarted via its own launchd label SIGTERM/KeepAlive. Authenticated Signed session200 after restart; user URL unchanged. Runtime scriptSHA changed8205c03f225d3f21adf0673b76b953b35cbe248599ebff5f82be96368d64731d→ffaafc97a1c7ca6d96de4f535057fb63ef3417f9b72b5b3cbb5f8dae3fea5dde. Other service copies were not installed or restarted.

## Verification

34 local gateway regressions pass, including one-response-only transport faults, no POST replay, exact signature/Host/Actor filtering, HEAD handling and real loopback listener class.

Actual Signed browser, cache disabled:1440/390/360 widths ×3 reloads,117 observed responses, no5xx, AI ready9/9 and horizontal overflow0/9. Then3 simultaneous browser tabs,41 observed h2 responses, no5xx. Six existing approved Composed/Freeform PNG/Caption/Receipt fetches all200 and exact expectedSHA (these are read-only recovery checks, not new model generation). Tailscale daemon error capture during the first post-fix series contained no proxy connection reset. Capture is a finite test, not an unlimited-load or permanent-zero-error SLA.

Evidence:/Users/Shared/ittem-bp18-codex-evidence-20261112/get-root-cause/
listener-before.txt, listener-after.txt, gateway-install.json, gateway-tests.log, browser-after.json, concurrent-browser-and-artifacts.json, after-{1440,390,360}.png. The pre-fix daemon two-line observation is recorded as a tool-output transcript, not presented as an original retained daemon log. daemon_proxy_log.log is the post-fix capture.

Current release status NOT_RELEASE_READY. C independent acceptance, image quality/HUMAN acceptance and invoice reconciliation remain separate.
