"""Shared claim and citation checks with no Provider imports or network IO."""
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CLAIM_SECTIONS = ("market_insights", "similar_products", "display_summary")


def claim_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def citation_url(url: object) -> str | None:
    """Accept only HTTP(S) links and remove tracking parameters."""
    if not isinstance(url, str) or len(url) > 2048 or "\\" in url or any(
        char.isspace() or not char.isprintable() for char in url
    ):
        return None
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or (
            parts.username is not None or parts.password is not None
        ):
            return None
        parts.port  # Reject malformed ports before exposing a clickable URL.
        query = parse_qsl(parts.query, keep_blank_values=True)
    except ValueError:
        return None
    filtered = [(key, value) for key, value in query if not key.lower().startswith("utm_")]
    if filtered != query:
        return urlunsplit(parts._replace(query=urlencode(filtered)))
    return url
