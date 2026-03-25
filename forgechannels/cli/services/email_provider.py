"""Detect email provider via MX record lookup."""

import dns.resolver

PROVIDER_PATTERNS = [
    ("google", [
        "google.com",
        "googlemail.com",
        "aspmx.l.google.com",
    ]),
    ("microsoft", [
        "outlook.com",
        "office365.com",
        "protection.outlook.com",
        "mail.protection.outlook.com",
    ]),
]

FREE_DOMAINS = {
    "gmail.com": "google",
    "googlemail.com": "google",
    "outlook.com": "microsoft",
    "hotmail.com": "microsoft",
    "live.com": "microsoft",
}


def get_mx_records(domain: str) -> list[str]:
    """Return MX hostnames for a domain, sorted by priority."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return [str(r.exchange).rstrip(".").lower() for r in sorted(answers, key=lambda r: r.preference)]
    except Exception:
        return []


def detect_provider(email: str) -> str:
    """Detect email provider. Returns 'google', 'microsoft', or 'unknown'."""
    email = email.strip().lower()
    if "@" not in email:
        return "unknown"

    domain = email.split("@", 1)[1]

    # Fast path: known free domains
    if domain in FREE_DOMAINS:
        return FREE_DOMAINS[domain]

    # MX record lookup
    mx_records = get_mx_records(domain)
    if not mx_records:
        return "unknown"

    for provider, patterns in PROVIDER_PATTERNS:
        for mx in mx_records:
            for pattern in patterns:
                if pattern in mx:
                    return provider

    return "unknown"


def provider_display_name(provider: str) -> str:
    """Human-readable provider name."""
    return {
        "google": "Google Chat",
        "microsoft": "Microsoft Teams",
        "unknown": "Unknown",
    }.get(provider, provider)
