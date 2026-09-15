#!/usr/bin/env python3
"""Secure, interactive setup. Secret input is never echoed or saved to files."""
import argparse
import getpass
import json
import secrets
import subprocess

from watch import REPOSITORY, request


def save_secret(name, value):
    subprocess.run(["gh", "secret", "set", name, "--repo", REPOSITORY],
                   input=value, text=True, check=True, capture_output=True)
    print(f"Saved {name} to GitHub Secrets.")


def configure_notifications():
    token = getpass.getpass("ntfy access token (hidden): ").strip()
    email = input("Verified alert email: ").strip()
    topic = "nyff-" + secrets.token_hex(20)
    if not token or "@" not in email:
        raise ValueError("An ntfy access token and verified email are required")
    save_secret("NTFY_TOKEN", token)
    save_secret("ALERT_EMAIL", email)
    save_secret("NTFY_TOPIC", topic)
    print("\nSubscribe to this topic in the ntfy phone app (server: https://ntfy.sh):")
    print(topic)
    print("Keep the topic private. Subscribe only to this topic; the email-copy topic is separate.")


def configure_health():
    key = getpass.getpass("Healthchecks project read-write API key (hidden): ").strip()
    headers = {"X-Api-Key": key}
    channels = json.loads(request("https://healthchecks.io/api/v3/channels/", headers=headers)[0])["channels"]
    email = [c for c in channels if c.get("name") == "NYFF email" and c.get("kind") == "email"]
    phone = [c for c in channels if c.get("name") == "NYFF phone" and c.get("kind") in {"webhook", "ntfy"}]
    if len(email) != 1 or len(phone) != 1:
        raise ValueError("Create and test integrations named 'NYFF email' and 'NYFF phone' in the dedicated Healthchecks project first")
    existing = json.loads(request("https://healthchecks.io/api/v3/checks/?tag=nyff2026", headers=headers)[0])["checks"]
    save_secret("HC_API_KEY", key)
    for component in ("feed", "page"):
        slug = "nyff2026-" + component
        found = [check for check in existing if check.get("slug") == slug]
        if len(found) > 1:
            raise ValueError("Duplicate NYFF health-check slugs; resolve in Healthchecks before continuing")
        body = {"name": "NYFF " + component, "slug": slug, "tags": "nyff2026",
                "desc": "Five-minute NYFF monitor. Explicit failure after three failed polls; silence alert after 30 minutes.",
                "timeout": 300, "grace": 1500, "channels": email[0]["id"] + "," + phone[0]["id"],
                "manual_resume": False}
        url = "https://healthchecks.io/api/v3/checks/" + (found[0]["uuid"] if found else "")
        created = json.loads(request(url, payload=body, headers=headers)[0])
        save_secret("HC_" + component.upper() + "_URL", created["ping_url"])
    print("Both checks configured: five-minute period plus 25-minute grace.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=["notifications", "health"])
    args = parser.parse_args()
    try:
        configure_notifications() if args.step == "notifications" else configure_health()
    except Exception as error:
        print(f"Setup needs attention ({type(error).__name__}). Check the account setup instructions; credentials were not printed.")
        raise SystemExit(1)
