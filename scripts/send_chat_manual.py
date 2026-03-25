#!/usr/bin/env python3
"""
Send a chat message via browser automation (no API keys required).
Uses your existing Google / Teams browser session.

Supports:
  - Google Workspace / Gmail  → Google Chat (chat.google.com)
  - Microsoft 365 / Outlook   → Microsoft Teams (teams.microsoft.com)

Install:
  pip install playwright
  playwright install chromium

Usage:
  # Send to all contacts in CSV (uses email_provider column)
  python send_chat_manual.py --csv demo_contacts.csv

  # Dry run — show what would be sent
  python send_chat_manual.py --csv demo_contacts.csv --dry-run

  # Single contact
  python send_chat_manual.py --email alice@gmail.com --provider "Google Workspace / Gmail" --message "Hey Alice!"

  # Keep browser open after each send (to verify)
  python send_chat_manual.py --csv demo_contacts.csv --pause
"""

import argparse
import csv
import pathlib
import sys
import time

GOOGLE_PROVIDERS = {"Google Workspace / Gmail"}
TEAMS_PROVIDERS = {"Microsoft 365 / Outlook"}

DEFAULT_MESSAGE = (
    "Hey {first_name}! Reaching out via ForgeChannels — "
    "we help sales teams cut through the noise by meeting prospects where they actually work. "
    "Would love to show you a quick demo. Open to a 15-min chat this week?"
)

# ── CSV ───────────────────────────────────────────────────────────────────────

def load_contacts(csv_path: str) -> list[dict]:
    p = pathlib.Path(csv_path)
    if not p.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_message(template: str, row: dict) -> str:
    fields = {k.lower().replace(" ", "_"): v for k, v in row.items()}
    fields.setdefault("first_name", fields.get("first name", fields.get("name", "there").split()[0]))
    fields.setdefault("last_name", fields.get("last name", ""))
    fields.setdefault("company", fields.get("company", "your company"))
    try:
        return template.format(**fields)
    except KeyError:
        return template


# ── Google Chat ───────────────────────────────────────────────────────────────

def send_google_chat(page, email: str, message: str, pause: bool) -> bool:
    print(f"    Opening Google Chat...")
    page.goto("https://chat.google.com", wait_until="networkidle")
    time.sleep(2)

    # Click "New chat" / start DM button
    try:
        # Try the pencil/compose icon
        new_chat = page.locator('[aria-label="New chat"], [data-tooltip="New chat"], button[jsname="r5"],  [aria-label="Start a new chat"]').first
        new_chat.click(timeout=8000)
        time.sleep(1)
    except Exception:
        print(f"    Could not find 'New chat' button — are you logged into chat.google.com?")
        return False

    # Type the email into the search/people field
    try:
        search = page.locator('input[aria-label*="people"], input[placeholder*="name"], input[aria-label*="Search"]').first
        search.click(timeout=5000)
        search.type(email, delay=60)
        time.sleep(2)
    except Exception:
        print(f"    Could not find recipient input field.")
        return False

    # Select the first suggestion
    try:
        suggestion = page.locator('[role="option"], [role="listitem"]').first
        suggestion.click(timeout=6000)
        time.sleep(1)
    except Exception:
        print(f"    No suggestion appeared for {email} — they may not be on Google Chat.")
        return False

    # Press Enter or click Open/Start
    try:
        open_btn = page.locator('button:has-text("Open"), button:has-text("Done"), button:has-text("Chat")').first
        open_btn.click(timeout=4000)
        time.sleep(1)
    except Exception:
        page.keyboard.press("Enter")
        time.sleep(1)

    # Type and send the message
    try:
        msg_box = page.locator('[aria-label*="message"], [contenteditable="true"][role="textbox"]').last
        msg_box.click(timeout=5000)
        msg_box.type(message, delay=30)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(1)
        print(f"    Sent via Google Chat.")
        if pause:
            input("    [paused] Press Enter to continue...")
        return True
    except Exception as e:
        print(f"    Could not type/send message: {e}")
        return False


# ── Microsoft Teams ───────────────────────────────────────────────────────────

def send_teams_message(page, email: str, message: str, pause: bool) -> bool:
    print(f"    Opening Microsoft Teams...")
    page.goto("https://teams.microsoft.com", wait_until="networkidle")
    time.sleep(3)

    # Click "New chat" icon
    try:
        new_chat = page.locator('[aria-label="New chat"], [data-tid="new-chat-button"], button[title="New chat"]').first
        new_chat.click(timeout=8000)
        time.sleep(1)
    except Exception:
        print(f"    Could not find 'New chat' button — are you logged into teams.microsoft.com?")
        return False

    # Type the email into the To: field
    try:
        to_field = page.locator('input[aria-label*="To"], input[placeholder*="name, email"]').first
        to_field.click(timeout=5000)
        to_field.type(email, delay=60)
        time.sleep(2)
    except Exception:
        print(f"    Could not find To: field.")
        return False

    # Select the first suggestion
    try:
        suggestion = page.locator('[role="option"]').first
        suggestion.click(timeout=6000)
        time.sleep(1)
    except Exception:
        print(f"    No suggestion for {email} — they may not be reachable via Teams external access.")
        return False

    # Type and send the message
    try:
        msg_box = page.locator('[aria-label*="Type a message"], div[contenteditable="true"][role="textbox"]').last
        msg_box.click(timeout=5000)
        msg_box.type(message, delay=30)
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(1)
        print(f"    Sent via Microsoft Teams.")
        if pause:
            input("    [paused] Press Enter to continue...")
        return True
    except Exception as e:
        print(f"    Could not type/send message: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send Google Chat / Teams messages via browser automation.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", help="Path to contacts CSV with email_provider column")
    group.add_argument("--email", help="Single recipient email")
    parser.add_argument("--provider", help="Provider for single email mode (e.g. 'Google Workspace / Gmail')")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Message template")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--pause", action="store_true", help="Pause after each send to verify")
    parser.add_argument("--headed", action="store_true", default=True, help="Show browser window (default: on)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    # Build contact list
    if args.csv:
        contacts = load_contacts(args.csv)
        provider_col = next((h for h in (contacts[0].keys() if contacts else []) if "provider" in h.lower()), None)
        if not provider_col:
            print("Warning: no email_provider column — run detect_email_provider.py first.")
        contacts = [c for c in contacts if c.get(provider_col, "") in GOOGLE_PROVIDERS | TEAMS_PROVIDERS]
    else:
        if not args.provider:
            print("--provider is required when using --email", file=sys.stderr)
            sys.exit(1)
        contacts = [{"email": args.email, "email_provider": args.provider, "first_name": args.email.split("@")[0]}]
        provider_col = "email_provider"

    if not contacts:
        print("No Google Chat or Teams contacts found. Run detect_email_provider.py first.")
        sys.exit(0)

    google = [c for c in contacts if c.get(provider_col, "") in GOOGLE_PROVIDERS]
    teams  = [c for c in contacts if c.get(provider_col, "") in TEAMS_PROVIDERS]
    print(f"Contacts: {len(google)} Google Chat, {len(teams)} Teams\n")

    if args.dry_run:
        print("DRY RUN — messages that would be sent:\n")
        for row in contacts:
            print(f"  [{row.get(provider_col, '?')}] {row.get('email', '')}")
            print(f"  {format_message(args.message, row)}\n")
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Run:\n  pip install playwright && playwright install chromium")
        sys.exit(1)

    headless = args.headless

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless, slow_mo=50)

        # Separate browser contexts so Google and Teams sessions are independent
        if google:
            print("=== Google Chat ===")
            ctx_google = browser.new_context()
            page_google = ctx_google.new_page()
            print("Please log into your Google account in the browser window, then press Enter here...")
            page_google.goto("https://accounts.google.com")
            input("  (logged in?) Press Enter to continue: ")

            sent = failed = 0
            for row in google:
                email = row.get("email", "").strip()
                msg = format_message(args.message, row)
                print(f"\n  → {email}")
                ok = send_google_chat(page_google, email, msg, args.pause)
                if ok: sent += 1
                else: failed += 1

            print(f"\n  Google Chat — Sent: {sent}  Failed: {failed}\n")
            ctx_google.close()

        if teams:
            print("=== Microsoft Teams ===")
            ctx_teams = browser.new_context()
            page_teams = ctx_teams.new_page()
            print("Please log into your Microsoft account in the browser window, then press Enter here...")
            page_teams.goto("https://teams.microsoft.com")
            input("  (logged in?) Press Enter to continue: ")

            sent = failed = 0
            for row in teams:
                email = row.get("email", "").strip()
                msg = format_message(args.message, row)
                print(f"\n  → {email}")
                ok = send_teams_message(page_teams, email, msg, args.pause)
                if ok: sent += 1
                else: failed += 1

            print(f"\n  Teams — Sent: {sent}  Failed: {failed}\n")
            ctx_teams.close()

        browser.close()

    print("All done.")


if __name__ == "__main__":
    main()
