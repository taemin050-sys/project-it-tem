"""Join a revision's recorded Provider usage to the independent cost ledger."""
import json

from .contracts import LiveGateError, digest


def verify_revision_cost(flow, evidence, actor, job_id, stage, fingerprint):
    try:
        row = flow.cost.inspect(evidence["attempt_id"])
        receipt = json.loads(row["receipt"])
        if (row["actor"] != actor or row["job_id"] != job_id or row["stage"] != stage
                or row["billing_unknown"] or row["status"] != "SUCCEEDED_USAGE_UNPRICED"
                or row["payload_hash"] != digest(fingerprint)
                or digest(receipt) != evidence["receipt_sha"]
                or receipt["model"] != evidence["response_model"]):
            raise ValueError
        return receipt
    except (KeyError, TypeError, ValueError):
        raise LiveGateError("REVISION_PROVIDER_COST_RECEIPT_INTEGRITY") from None
