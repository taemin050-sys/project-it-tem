"""Checkbox attestation of the bound copy; legacy transcripts remain readable."""
def copy_review_valid(checks, approved_copy, required):
    if not isinstance(checks, dict):
        return False
    required=set(required)
    if any(checks.get(field) is not True for field in required):
        return False
    if set(checks)==required|{"copy_verified"}:
        return checks["copy_verified"] is True
    if set(checks)==required|{"observed_copy"}:
        return checks["observed_copy"]==approved_copy
    return False
