#!/usr/bin/env python3
"""
Detect the email provider for a given email address via MX record lookup.

Usage:
    # Single emails

    # CSV mode — auto-detects the email column, adds an 'email_provider' column
    python detect_email_provider.py contacts.csv
    python detect_email_provider.py contacts.csv --email-col work_email
"""

import csv
import sys
import pathlib
import dns.resolver

PROVIDER_PATTERNS = [
    ("Google Workspace / Gmail", [
        "google.com",
        "googlemail.com",
        "aspmx.l.google.com",
    ]),
    ("Microsoft 365 / Outlook", [
        "outlook.com",
        "office365.com",
        "protection.outlook.com",
        "mail.protection.outlook.com",
    ]),
    ("Zoho Mail", [
        "zoho.com",
        "zohomail.com",
    ]),
    ("Yahoo Mail", [
        "yahoo.com",
        "yahoodns.net",
    ]),
    ("ProtonMail", [
        "protonmail.ch",
        "proton.me",
    ]),
    ("Fastmail", [
        "fastmail.com",
        "messagingengine.com",
    ]),
    ("iCloud Mail", [
        "icloud.com",
        "me.com",
        "mac.com",
    ]),
    ("Mimecast", [
        "mimecast.com",
    ]),
    ("SendGrid", [
        "sendgrid.net",
    ]),
    ("Amazon SES", [
        "amazonses.com",
        "amazonaws.com",
    ]),
]


def get_mx_records(domain: str) -> list[str]:
    """Return a list of MX hostnames for the given domain, sorted by priority."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return [str(r.exchange).rstrip(".").lower() for r in sorted(answers, key=lambda r: r.preference)]
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        return []
    except Exception:
        return []


def detect_provider(email: str) -> dict:
    """
    Given an email address, return a dict with:
        email, domain, provider, mx_records, confidence
    """
    email = email.strip().lower()
    if "@" not in email:
        return {"email": email, "domain": None, "provider": "Invalid email", "mx_records": [], "confidence": 0.0}

    domain = email.split("@", 1)[1]
    mx_records = get_mx_records(domain)

    # Check free consumer providers by domain first (fast path)
    free_providers = {
        "gmail.com": "Google Workspace / Gmail",
        "googlemail.com": "Google Workspace / Gmail",
        "outlook.com": "Microsoft 365 / Outlook",
        "hotmail.com": "Microsoft 365 / Outlook",
        "live.com": "Microsoft 365 / Outlook",
        "yahoo.com": "Yahoo Mail",
        "yahoo.co.uk": "Yahoo Mail",
        "protonmail.com": "ProtonMail",
        "proton.me": "ProtonMail",
        "icloud.com": "iCloud Mail",
        "me.com": "iCloud Mail",
        "mac.com": "iCloud Mail",
        "fastmail.com": "Fastmail",
        "fastmail.fm": "Fastmail",
        "zoho.com": "Zoho Mail",
    }
    if domain in free_providers:
        return {
            "email": email,
            "domain": domain,
            "provider": free_providers[domain],
            "mx_records": mx_records or [f"(known domain — skipped DNS)"],
            "confidence": 1.0,
        }

    if not mx_records:
        return {
            "email": email,
            "domain": domain,
            "provider": "Unknown (no MX records found)",
            "mx_records": [],
            "confidence": 0.0,
        }

    # Match MX records against known provider patterns
    for provider_name, patterns in PROVIDER_PATTERNS:
        for mx in mx_records:
            for pattern in patterns:
                if pattern in mx:
                    confidence = 1.0 if mx_records[0] and pattern in mx_records[0] else 0.85
                    return {
                        "email": email,
                        "domain": domain,
                        "provider": provider_name,
                        "mx_records": mx_records,
                        "confidence": confidence,
                    }

    return {
        "email": email,
        "domain": domain,
        "provider": "Unknown / Self-hosted",
        "mx_records": mx_records,
        "confidence": 0.0,
    }


def print_result(result: dict) -> None:
    provider = result["provider"]
    confidence = result["confidence"]
    domain = result["domain"] or "—"
    mx = result["mx_records"]

    conf_str = f"{confidence:.0%}" if confidence > 0 else "n/a"
    print(f"  email    : {result['email']}")
    print(f"  domain   : {domain}")
    print(f"  provider : {provider}")
    print(f"  confidence: {conf_str}")
    if mx and not mx[0].startswith("(known"):
        print(f"  mx       : {mx[0]}" + (f" (+{len(mx)-1} more)" if len(mx) > 1 else ""))
    print()


EMAIL_COL_CANDIDATES = ["email", "email_address", "work_email", "e-mail", "mail"]


def find_email_column(headers: list[str]) -> str | None:
    lower = [h.lower().strip() for h in headers]
    for candidate in EMAIL_COL_CANDIDATES:
        if candidate in lower:
            return headers[lower.index(candidate)]
    # fallback: first column that contains the word "email"
    for i, h in enumerate(lower):
        if "email" in h or "mail" in h:
            return headers[i]
    return None


def process_csv(path: str, email_col: str | None = None) -> None:
    p = pathlib.Path(path)
    if not p.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(p, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows = list(reader)

    col = email_col or find_email_column(headers)
    if not col:
        print(f"Error: could not find an email column. Headers: {headers}", file=sys.stderr)
        print("Use --email-col <column_name> to specify it.", file=sys.stderr)
        sys.exit(1)

    if col not in headers:
        print(f"Error: column '{col}' not found. Headers: {headers}", file=sys.stderr)
        sys.exit(1)

    out_col = "email_provider"
    if out_col in headers:
        new_headers = headers  # overwrite existing column
    else:
        new_headers = headers + [out_col]

    print(f"Processing {len(rows)} rows using column '{col}'...")

    domain_cache: dict[str, str] = {}

    for i, row in enumerate(rows, 1):
        email = row.get(col, "").strip()
        if not email:
            row[out_col] = ""
            continue

        domain = email.split("@", 1)[1].lower() if "@" in email else ""
        if domain in domain_cache:
            provider = domain_cache[domain]
        else:
            result = detect_provider(email)
            provider = result["provider"]
            if domain:
                domain_cache[domain] = provider

        row[out_col] = provider
        print(f"  [{i}/{len(rows)}] {email} → {provider}")

    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=new_headers)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. '{out_col}' column written to {p}")


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: detect_email_provider.py <email> [email2 ...]")
        print("       detect_email_provider.py contacts.csv [--email-col <col>]")
        sys.exit(1)

    # CSV mode
    if args[0].endswith(".csv"):
        email_col = None
        if "--email-col" in args:
            idx = args.index("--email-col")
            if idx + 1 < len(args):
                email_col = args[idx + 1]
        process_csv(args[0], email_col)
        return

    # Single email mode
    emails = []
    if args == ["-"]:
        emails = [line.strip() for line in sys.stdin if line.strip()]
    else:
        emails = args

    for email in emails:
        result = detect_provider(email)
        print_result(result)


if __name__ == "__main__":
    main()
