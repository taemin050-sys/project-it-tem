# PR18 — Real React QA-only offline fixture E2E contract

QA requires the isolated backend IT_TEM_QA_FIXTURE_ENABLED=YES and a separate React bundle VITE_QA_OFFLINE_FIXTURE=YES. The backend also requires Live execution disabled, loopback client, local-only cookie and allowlisted authenticated QA actor. Default is OFF.

QA endpoint routes reuse official Owner Text DTO, rule compliance, approval, Owner A safe_zone, Korean composition and SHA manifest, but images and text are static OFFLINE_FIXTURE test data. Zero OpenAI provider calls and zero billing attempts.

Normal Live-only queue, artifact endpoints, sharing and evaluation still reject OFFLINE_FIXTURE. The UI displays a persistent QA banner and fixture provenance badge across original ProductPage/CopyPage/DraftPage/ExportPage screens.

Only the static unit-test brand '라움' is supported by this fixture; other brands fail closed. No actual product photo recognition, product preservation, AI quality or Live performance may be inferred.

This QA runtime must never be served through the existing 8443 Tailnet path or exposed externally with test credentials. GCP port 18082 only, no team demo or official PR modifications. QA browser screenshots and actual Live E2E remain separately classified.
