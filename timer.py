"""Queue a ticket check and the next five-minute GitHub environment wait."""
import base64
import json
import os
import sys
from datetime import timedelta

from watch import FetchError, REPOSITORY, TARGETS, date, request, utcnow


def run_timer(env, ensure=False):
    headers = {"Authorization": "Bearer " + env["GH_TOKEN"],
               "Accept": "application/vnd.github+json", "Cache-Control": "no-cache"}

    def api(path, payload=None):
        body, _ = request(f"https://api.github.com/repos/{REPOSITORY}/" + path,
                          headers=headers, payload=payload, timeout=10, retries=2)
        return json.loads(body) if body else None

    now = utcnow()
    # Fail closed if the environment delay is removed or bypassed. This prevents
    # a configuration mistake from creating a rapid self-dispatch loop.
    if not ensure:
        run = api("actions/runs/" + env["GITHUB_RUN_ID"])
        if now - date(run["created_at"]) < timedelta(seconds=295):
            raise ValueError("The five-minute GitHub wait timer has not elapsed")
    if api("")["private"]:
        raise ValueError("Automatic timer requires the configured public repository")
    content = api("contents/state.json?ref=data")
    state = json.loads(base64.b64decode(content["content"]))
    if state.get("version") != 1:
        raise ValueError("Invalid observation state")
    if state.get("stopped") and state.get("shutdown_complete"):
        print("Ticket monitoring is complete; timer chain ended.")
        return
    expiry = max(date(state["screenings"].get(pid, {}).get("start", start))
                 for pid, (start, _) in TARGETS.items())
    if ensure:
        runs = api("actions/workflows/timer.yml/runs?per_page=10")["workflow_runs"]
        if any(run["status"] != "completed" for run in runs):
            print("Automatic timer is already active.")
        else:
            api("actions/workflows/timer.yml/dispatches", {"ref": "main"})
            print("Restarted automatic timer from the backup schedule.")
        return
    try:
        api("actions/workflows/watch.yml/dispatches", {"ref": "main", "inputs": {"operation": "auto"}})
        if state.get("stopped") or now >= expiry:
            print("Queued shutdown cleanup; retries continue until cleanup succeeds.")
        else:
            print("Queued an automatic check of all four screenings.")
    finally:
        # A failed ticket-check dispatch must not permanently break the clock.
        api("actions/workflows/timer.yml/dispatches", {"ref": "main"})
        print("Queued the next five-minute wait.")


if __name__ == "__main__":
    try:
        run_timer(os.environ, ensure="--ensure" in sys.argv[1:])
    except (FetchError, ValueError, KeyError) as exc:
        print(f"::error::Timer failed ({type(exc).__name__}); check the wait environment and workflow permissions.")
        sys.exit(1)
