# IT-TEM Product Live Team Evaluation UI — QA / Release

- Scope: style and accessible labeling of the team evaluation page, reusing Owner FE tokens/classes without editing Owner CSS, B0 endpoints, Live JobStore, or provider logic.
- Branch: fix/ittem-live-uix-20261101, parent: b4fab0e872ff0139662636f3ad59cf161250d6d1.
- Retain existing Live API routes, read-only shares, private source assets, user-specific evaluations, no auto-paid requests.
- Build must set VITE_IT_TEM_CODE_SHA to the HEAD commit SHA; reject any browser acceptance with UNPINNED or mismatched SHA.
- Browser QA at 1320px and 390px: team evaluation list, ad preview, category, score, comment, no horizontal overflow, no JS/HTTP errors, no Live POST.
- Full Owner workflow /create/* remains unchanged; verify no regression before PM/UAT.
- Human team independent ratings and legal adequacy remain pending; automated UI checks do not count as participants.
- Deployment must preserve prior immutable GCP release, SQLite queue/receipts/assets, and rollback path.
