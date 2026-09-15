"""Public, credential-free summary for GitHub's run page."""
import json
from pathlib import Path
import sys
from watch import TARGETS, fallback_record, readable

path = Path(sys.argv[1]) / "state.json"
if not path.exists():
    print("Observation state has not been saved. Check the failed step above.")
else:
    state = json.loads(path.read_text())
    print("# NYFF ticket monitor\n")
    print("Status: **" + ("Stopped" if state.get("stopped") else "Collecting observations") + "**\n")
    print("Last automatic check: **" + state.get("last_automatic_poll", "Awaiting first automatic check") + "**\n")
    print("| Screening | Status | Rush |\n|---|---|---|")
    for pid in TARGETS:
        item = state["screenings"].get(pid, fallback_record(pid))
        rush = item.get("rush") or state.get("page_rush", {}).get(pid, {}).get("rush")
        print(f"| {readable(item['start'])} · {item['venue']} | {item['status']} | {'Yes' if rush else 'No observed designation'} |")
    print("\n## Setup\n")
    for key, configured in state.get("configuration", {}).items():
        print(f"- {key}: {'configured' if configured else '**setup required**'}")
    print("\n## Components\n")
    for name, component in state.get("components", {}).items():
        print(f"- {name}: {component.get('failures', 0)} consecutive failures; last success {component.get('last_success', 'pending')}.")
    print("\n[Release history and report](https://github.com/karthiktadepalli1/nyff-watch/tree/data) · [Monitor controls](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml)")
