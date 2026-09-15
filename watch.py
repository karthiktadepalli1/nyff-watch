#!/usr/bin/env python3
"""NYFF availability, rush detection, durable alerts, and release history.

Only public NYFF content enters the data branch. Notification credentials stay
in the environment. Python 3.11+; standard library only.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
FEED_URL = "https://api.filmlinc.org/content/festivals/nyff2026"
PAGE_URL = "https://www.filmlinc.org/nyff2026/films/all-of-a-sudden/"
REPOSITORY = "karthiktadepalli1/nyff-watch"
OPEN = {"available", "limited"}
TARGETS = {
    "84274": ("2026-10-01T17:00:00-04:00", "Alice Tully Hall"),
    "84281": ("2026-10-02T14:00:00-04:00", "Alice Tully Hall"),
    "84158": ("2026-10-04T19:30:00-04:00", "Francesca Beale Theater"),
    "84159": ("2026-10-09T12:30:00-04:00", "Walter Reade Theater"),
}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def utcnow():
    return datetime.now(timezone.utc)


def stamp(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def date(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Datetime must include a timezone")
    return result


def readable(value):
    return date(value).astimezone(ET).strftime("%a %b %d, %-I:%M %p ET")


def clean(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", str(value or ""))).split())


def ids(value):
    if isinstance(value, list):
        return [item for v in value for item in ids(v)]
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


def initial_state():
    return {"version": 1, "stopped": False, "screenings": {}, "page_rush": {},
            "components": {}, "outbox": [], "email_budget": {}, "runs": [],
            "configuration": {}, "notification_failures": 0}


class FetchError(Exception):
    """A deliberately credential-free network error."""


def request(url, *, payload=None, headers=None, method=None, timeout=15, retries=2):
    base = {"User-Agent": f"Mozilla/5.0 (compatible; NYFFWatch/1.0; +https://github.com/{REPOSITORY})"}
    base.update(headers or {})
    data = json.dumps(payload).encode() if isinstance(payload, (dict, list)) else payload
    if isinstance(payload, (dict, list)):
        base.setdefault("Content-Type", "application/json")
    host = urllib.parse.urlparse(url).hostname
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=base, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read().decode("utf-8"), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            transient = exc.code in {408, 429} or exc.code >= 500
            error = f"HTTP {exc.code} from {host}"
            exc.close()
        except (urllib.error.URLError, TimeoutError, OSError):
            transient, error = True, f"Network error contacting {host}"
        if not transient or attempt == retries:
            raise FetchError(error)
        time.sleep((2, 5)[min(attempt, 1)])


def cache_metadata(headers):
    h = {k.lower(): v for k, v in headers.items()}
    return {k: h.get(k) for k in ("date", "age", "cache-control", "etag", "last-modified", "x-vercel-cache", "cf-cache-status")}


def expected_ids(state, now):
    return {pid for pid, (start, _) in TARGETS.items()
            if date(state["screenings"].get(pid, {}).get("start", start)) > now}


def parse_feed(payload, expected):
    films = payload.get("filmsWithShowtimes")
    if payload.get("slug") != "nyff2026" or not isinstance(films, list) or not films:
        raise ValueError("Unexpected festival feed")
    result, target_found = {}, False
    for film in films:
        if film.get("slug") == "all-of-a-sudden":
            target_found = True
        promotions = {}
        details = film.get("filmDetails") or film.get("eventDetails") or {}
        for event in details.get("specialEvents") or []:
            if not event:
                continue
            codes = ids(event.get("promoShort"))
            # The site selects the first promotion code and the last matching record.
            promo = codes[0].lower() if codes else ""
            for pid in ids(event.get("tessituraId")):
                promotions[pid] = (promo, clean(event.get("promoTooltip") or event.get("subhead") or event.get("heading")))
        for show in film.get("showtimes") or []:
            pid = str(show.get("id", ""))
            if not pid or not isinstance(show.get("status"), str):
                raise ValueError("Screening has no ID or status")
            start = show.get("dateTimeET")
            date(start)  # Reject a partial response before overwriting valid state.
            if pid in TARGETS and film.get("slug") != "all-of-a-sudden":
                raise ValueError("Target screening belongs to an unexpected film")
            promo, explanation = promotions.get(pid, (show.get("promoShort") or "", clean(show.get("promoTooltip"))))
            record = {"id": pid, "film": clean(film.get("title")), "slug": film.get("slug"),
                      "start": start, "venue": clean(show.get("venue")),
                      "status": show["status"].lower(), "available": show.get("available"),
                      "no_standby": bool(show.get("noStandby")), "rush": promo == "rush",
                      "rush_text": explanation if promo == "rush" else "",
                      "url": show.get("ticketsUrl") or ""}
            if pid in result and result[pid] != record:
                raise ValueError("Conflicting duplicate screening records")
            result[pid] = record
    if not target_found or not expected.issubset(result):
        raise ValueError("Target film or upcoming screening missing from feed")
    return result


class RushPageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.records, self.visible = [], defaultdict(list), []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        blocked = (self.stack and self.stack[-1][2]) or tag in {"script", "style", "template"}
        pid = attributes.get("data-performance-id")
        inherited = self.stack[-1][1] if self.stack else None
        active = pid or inherited
        if pid and not blocked:
            self.records[pid].append("")
        if tag not in VOID_TAGS:
            self.stack.append((tag, active, blocked))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        if self.stack and self.stack[-1][2]:
            return
        self.visible.append(text)
        if self.stack:
            pid = self.stack[-1][1]
            if pid in self.records and self.records[pid]:
                self.records[pid][-1] += " " + text


def parse_page(body, expected):
    parser = RushPageParser()
    parser.feed(body)
    visible = clean(" ".join(parser.visible))
    if "All of a Sudden" not in visible or not expected.issubset(parser.records):
        raise ValueError("Film page blocked, incomplete, or screening controls missing")
    return {pid: any(re.search(r"\brush\b", text, re.I) for text in texts)
            for pid, texts in parser.records.items() if pid in TARGETS}


def add_alert(state, kind, record, now, message=None, sources=None):
    pid = record["id"]
    title = {"ticket": "Possible ticket release—check now", "rush": "NYFF rush tickets announced",
             "update": "NYFF screening update", "test": "TEST — NYFF monitor: all four screenings"}[kind]
    common = f"{record['film']}\n{readable(record['start'])} · {record['venue']}\nObserved {readable(stamp(now))}."
    if kind == "rush":
        start = date(record["start"])
        detail = (f"In-person purchase: $15 rush tickets, subject to availability. "
                  f"Box-office sales start {readable(stamp(start - timedelta(hours=1)))}. "
                  f"Suggested arrival: {readable(stamp(start - timedelta(minutes=90)))}.")
        message = "\n".join(filter(None, [detail, record.get("rush_text")]))
    elif kind == "ticket":
        message = "The official feed shows tickets available or limited. Open the purchase link to check for one seat."
    elif kind == "test":
        common = "All of a Sudden — monitoring all four screenings:\n" + "\n".join(
            f"{readable(state['screenings'].get(target, fallback_record(target))['start'])} · "
            f"{state['screenings'].get(target, fallback_record(target))['venue']}" for target in TARGETS)
        message = "Delivery test. You will be alerted if any of these screenings opens or announces rush tickets."
    event_id = hashlib.sha256(f"{kind}:{pid}:{stamp(now)}:{len(state['outbox'])}".encode()).hexdigest()[:24]
    state["outbox"].append({"id": event_id, "kind": kind, "performance_id": None if kind == "test" else pid,
                            "title": title, "message": common + "\n" + (message or ""),
                            "click": PAGE_URL if kind == "test" else record["url"], "created": stamp(now),
                            "expires": stamp(min(date(record["start"]), now + timedelta(hours=6))) if kind != "test" else stamp(now + timedelta(hours=1)),
                            "sources": sources or [], "push": "pending", "email": "pending",
                            "priority": 5 if kind in {"ticket", "rush"} else 3})


def component_result(state, name, now, error=None, metadata=None):
    component = state["components"].setdefault(name, {"failures": 0})
    component["last_attempt"] = stamp(now)
    if error:
        component["failures"] += 1
        component["error"] = error
    else:
        component.update({"failures": 0, "last_success": stamp(now), "error": None,
                          "cache": metadata or {}})


def observe(state, feed, page, errors, metadata, now):
    """Apply validated observations. Failed sources never erase their last state."""
    feed = copy.deepcopy(feed)
    old = copy.deepcopy(state["screenings"])
    events = []
    previous = state["components"].get("feed", {}).get("last_success")
    old_effective = {pid: (old.get(pid, {}).get("rush", False) or state["page_rush"].get(pid, {}).get("rush", False)) for pid in TARGETS}
    for name, value in (("feed", feed), ("page", page)):
        component_result(state, name, now, errors.get(name) if value is None else None, metadata.get(name))
    if feed is not None:
        for pid, item in feed.items():
            before = old.get(pid)
            if before != item:
                kind = "baseline" if not previous else "catalogue_addition" if before is None else "change"
                events.append({"observed_at": stamp(now), "previous_observed_at": previous,
                               "batch": stamp(now), "kind": kind, "id": pid, "film": item["film"],
                               "start": item["start"], "venue": item["venue"], "before": before,
                               "after": item, "cache": metadata.get("feed", {})})
            if pid in TARGETS and date(item["start"]) > now:
                if item["status"] in OPEN and (before is None or before["status"] not in OPEN):
                    add_alert(state, "ticket", item, now, sources=["feed"])
                if before:
                    changes = [f"{key.replace('_', ' ')}: {before.get(key)} → {item.get(key)}"
                               for key in ("start", "venue", "no_standby") if before.get(key) != item.get(key)]
                    if changes:
                        add_alert(state, "update", item, now, "; ".join(changes), ["feed"])
        # Keep records that vanish, but distinguish absence from an observed closure.
        state["screenings"].update(feed)
        state["present_ids"] = sorted(feed)
    if page is not None:
        for pid, rush in page.items():
            state["page_rush"][pid] = {"rush": rush, "observed_at": stamp(now)}
    for pid in TARGETS:
        item = state["screenings"].get(pid)
        if not item or date(item["start"]) <= now:
            continue
        # Page-only detection can work even before the first successful feed.
        current = item.get("rush", False) or state["page_rush"].get(pid, {}).get("rush", False)
        if current and not old_effective[pid]:
            sources = (["feed"] if item.get("rush") else []) + (["film page"] if state["page_rush"].get(pid, {}).get("rush") else [])
            add_alert(state, "rush", item, now, sources=sources)
    state.setdefault("started_at", stamp(now))
    state["last_poll"] = stamp(now)
    state["runs"].append({"at": stamp(now), "feed": feed is not None, "page": page is not None})
    state["runs"] = state["runs"][-600:]
    return events


def fallback_record(pid):
    start, venue = TARGETS[pid]
    return {"id": pid, "film": "All of a Sudden", "start": start, "venue": venue,
            "url": f"https://purchase.filmlinc.org/84110/{pid}", "status": "unknown", "rush": False}


def still_actionable(alert, state, now):
    if date(alert["expires"]) <= now:
        return False
    if alert["kind"] == "test":
        return True
    pid = alert["performance_id"]
    record = state["screenings"].get(pid, fallback_record(pid))
    if date(record["start"]) <= now or state.get("stopped"):
        return False
    if alert["kind"] == "ticket":
        return record["status"] in OPEN
    if alert["kind"] == "rush":
        return record.get("rush") or state["page_rush"].get(pid, {}).get("rush")
    return True


class Store:
    def __init__(self, folder, git=False):
        self.folder, self.git = Path(folder), git
        self.folder.mkdir(parents=True, exist_ok=True)

    def load(self):
        path = self.folder / "state.json"
        if not path.exists():
            return initial_state()
        state = json.loads(path.read_text())
        if state.get("version") != 1:
            raise ValueError("Unsupported state version")
        return state

    def save(self, state, events=()):
        path = self.folder / "state.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        temporary.replace(path)
        if events:
            with (self.folder / "changes.jsonl").open("a") as stream:
                for event in events:
                    stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        if self.git:
            def git(*args):
                return subprocess.run(["git", "-C", str(self.folder), *args], check=True, capture_output=True, text=True)
            git("add", "state.json")
            for filename in ("changes.jsonl", "report.md", "first24hours.md"):
                if (self.folder / filename).exists():
                    git("add", filename)
            if git("diff", "--cached", "--name-only").stdout:
                git("commit", "-m", "Update monitor observations")
            # Retry a previous successful local commit whose push failed.
            git("push", "origin", "HEAD:data")


def notify(alert, channel, env):
    token, topic = env.get("NTFY_TOKEN"), env.get("NTFY_TOPIC")
    if not token or not topic or (channel == "email" and not env.get("ALERT_EMAIL")):
        raise FetchError("Notification configuration incomplete")
    payload = {"topic": topic, "title": alert["title"], "message": alert["message"],
               "priority": alert["priority"], "tags": ["tickets"], "click": alert["click"]}
    if channel == "email":
        # A dedicated secondary topic prevents an email retry duplicating phone pushes.
        payload["topic"] = topic + "-email"
        payload["email"] = env["ALERT_EMAIL"]
    request("https://ntfy.sh/", payload=payload,
            headers={"Authorization": "Bearer " + token}, timeout=8, retries=0)


def deliver(state, store, now, env, sender=notify):
    failed = False
    # ntfy resets its free email allowance at midnight UTC.
    day = now.astimezone(timezone.utc).date().isoformat()
    if state["email_budget"].get("day") != day:
        state["email_budget"] = {"day": day, "attempts": 0}
    for alert in state["outbox"]:
        if not still_actionable(alert, state, now):
            for channel in ("push", "email"):
                if alert[channel] == "pending":
                    alert[channel] = "expired"
            continue
        for channel in ("push", "email"):
            if alert[channel] != "pending":
                continue
            if channel == "email":
                if state["email_budget"]["attempts"] >= 5:
                    continue
                if not env.get("ALERT_EMAIL") or not env.get("NTFY_TOKEN"):
                    failed = True
                    continue
                # Reserve before sending so a restarted run cannot exceed the budget.
                state["email_budget"]["attempts"] += 1
                store.save(state)
            try:
                sender(alert, channel, env)
                alert[channel] = "sent"
                alert[channel + "_sent_at"] = stamp(now)
                alert.pop(channel + "_error", None)
            except FetchError as error:
                failed = True
                alert[channel + "_error"] = str(error)
            store.save(state)
    state["notification_failures"] = state.get("notification_failures", 0) + 1 if failed else 0
    # Keep a bounded delivery audit; preserve every outstanding alert.
    cutoff = now - timedelta(days=7)
    state["outbox"] = [a for a in state["outbox"] if "pending" in (a["push"], a["email"]) or date(a["created"]) >= cutoff]
    store.save(state)


def health_ping_url(env, name):
    url = env.get("HC_" + name.upper() + "_URL", "")
    if url:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "hc-ping.com":
            raise ValueError("Invalid Healthchecks ping host")
        uuid.UUID(parsed.path.strip("/"))
    return url.rstrip("/")


def send_health(state, env):
    for name in ("feed", "page"):
        url = health_ping_url(env, name)
        if not url:
            continue
        component = state["components"].get(name, {})
        failures = component.get("failures", 0)
        if name == "feed":
            # This check is the single user-facing health alert. The page check
            # remains a silent diagnostic, avoiding two emails for one outage.
            failures = max(failures, state["components"].get("page", {}).get("failures", 0),
                           state.get("notification_failures", 0))
        if failures >= 3:
            if component.get("health_signal") == "down":
                continue
            suffix, signal = "/fail", "down"
        elif failures:
            continue
        else:
            suffix, signal = "", "up"
        try:
            label = "monitor" if name == "feed" else "page diagnostic"
            detail = (f"NYFF {label}: {signal}. "
                      f"Feed failures: {state['components'].get('feed', {}).get('failures', 0)}; "
                      f"page failures: {state['components'].get('page', {}).get('failures', 0)}; "
                      f"delivery failures: {state.get('notification_failures', 0)}.")
            request(url + suffix, payload=detail.encode(), timeout=8, retries=0)
            component["health_signal"] = signal
        except FetchError:
            print(f"::warning::Healthchecks {name} check-in failed")


def stop_monitor(state, store, now, env, reason):
    state.update(stopped=True, stopped_at=state.get("stopped_at", stamp(now)), stop_reason=reason)
    store.save(state)
    for name in ("feed", "page"):
        url = health_ping_url(env, name)
        if url:
            if not env.get("HC_API_KEY"):
                raise FetchError("Healthchecks API key required to pause checks")
            check_id = urllib.parse.urlparse(url).path.strip("/")
            request(f"https://healthchecks.io/api/v3/checks/{check_id}/pause", payload={},
                    headers={"X-Api-Key": env["HC_API_KEY"]}, timeout=8, retries=1)
    if env.get("GITHUB_ACTIONS") == "true":
        for workflow in ("timer.yml", "watch.yml"):
            request(f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/{workflow}/disable",
                    method="PUT", payload=b"", timeout=8, retries=1,
                    headers={"Authorization": "Bearer " + env["GH_TOKEN"], "Accept": "application/vnd.github+json"})
    print("Monitor stopped; configured health checks paused.")


def report(state, events):
    openings = [e for e in events if e["kind"] == "change" and e["before"]["status"] not in OPEN and e["after"]["status"] in OPEN]
    hours = Counter(date(e["observed_at"]).astimezone(ET).hour for e in openings)
    lead = Counter((date(e["start"]).astimezone(ET).date() - date(e["observed_at"]).astimezone(ET).date()).days for e in openings)
    batches = Counter(e["batch"] for e in openings)
    started, durations = {}, []
    for event in events:
        pid = event["id"]
        if event["after"]["status"] in OPEN:
            started.setdefault(pid, (date(event["observed_at"]), event["kind"] != "change"))
        elif pid in started:
            beginning, censored = started.pop(pid)
            if not censored:
                durations.append((date(event["observed_at"]) - beginning).total_seconds() / 60)
    runs = state.get("runs", [])
    gaps = [(date(b["at"]) - date(a["at"])).total_seconds() / 60 for a, b in zip(runs, runs[1:])]
    lines = ["# NYFF release observations", "", "Times are America/New_York. These are observed changes, not exact release times.",
             "Polling gaps and source caches can hide brief openings. Simultaneous changes may be a single batch.", "",
             f"Observed reopenings: **{len(openings)}** across **{len(batches)} batches**.", "",
             "## Openings by Eastern-time hour", "", "| Hour | Openings |", "|---|---:|"]
    lines += [f"| {hour:02d}:00–{hour:02d}:59 | {count} |" for hour, count in sorted(hours.items())]
    lines += ["", "## Days before screening", "", "| Days | Openings |", "|---|---:|"]
    lines += [f"| {days} | {count} |" for days, count in sorted(lead.items())]
    lines += ["", "## Observed open durations", "", f"Complete observed opening/closure pairs: {len(durations)}."]
    if durations:
        lines.append(f"Minimum / median / maximum: {min(durations):.1f} / {sorted(durations)[len(durations)//2]:.1f} / {max(durations):.1f} minutes.")
    lines += ["", "## Recent operation", "", f"Retained checks: {len(runs)}. Longest observed gap: {max(gaps, default=0):.1f} minutes.",
              f"Feed failures: {sum(not r['feed'] for r in runs)}; page failures: {sum(not r['page'] for r in runs)}.",
              "", "## Target screenings", "", "| Screening | Status | Rush |", "|---|---|---|"]
    for pid in TARGETS:
        item = state["screenings"].get(pid, fallback_record(pid))
        rush = item.get("rush") or state["page_rush"].get(pid, {}).get("rush", False)
        lines.append(f"| {readable(item['start'])} · {item['venue']} | {item['status']} | {'Yes' if rush else 'No observed designation'} |")
    lines += ["", "## Configuration", ""]
    lines += [f"- {key}: {'configured' if value else 'setup required'}" for key, value in state.get("configuration", {}).items()]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["poll", "auto", "test-alert", "report", "stop", "probe"])
    parser.add_argument("--data", default="data")
    parser.add_argument("--git", action="store_true", help="Commit and push state to the data branch")
    args = parser.parse_args()
    now, env = utcnow(), os.environ
    automatic = args.command == "auto" or env.get("GITHUB_EVENT_NAME") == "schedule"
    store = Store(args.data, args.git)
    state = store.load()
    state["configuration"] = {
        "phone_push": bool(env.get("NTFY_TOKEN") and env.get("NTFY_TOPIC")),
        "email": bool(env.get("NTFY_TOKEN") and env.get("ALERT_EMAIL")),
        "feed_health": bool(env.get("HC_FEED_URL") and env.get("HC_API_KEY")),
        "page_health": bool(env.get("HC_PAGE_URL") and env.get("HC_API_KEY")),
    }
    expiry = max(date(state["screenings"].get(pid, {}).get("start", start)) for pid, (start, _) in TARGETS.items())
    if args.command == "stop" or state.get("stopped") or (now >= expiry and args.command in {"poll", "auto"}):
        stop_monitor(state, store, now, env, "ticket secured" if args.command == "stop" else state.get("stop_reason", "final screening started"))
        return 0
    if automatic and state.get("last_automatic_poll") and now - date(state["last_automatic_poll"]) < timedelta(minutes=4):
        print("A recent automatic check already completed; duplicate trigger skipped.")
        return 0
    if args.command == "report":
        path = store.folder / "changes.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        output = report(state, events)
        (store.folder / "report.md").write_text(output)
        store.save(state)
        print(output)
        return 0
    if args.command == "test-alert":
        pid = next(iter(TARGETS))
        add_alert(state, "test", state["screenings"].get(pid, fallback_record(pid)), now)
        store.save(state)
        deliver(state, store, now, env)
        last = state["outbox"][-1]
        print(f"Test delivery: phone={last['push']}, email={last['email']}")
        return 0 if last["push"] == last["email"] == "sent" else 1
    expected = expected_ids(state, now)
    feed = page = None
    errors, metadata = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending = {name: pool.submit(request, url, headers={"Cache-Control": "no-cache"})
                   for name, url in (("feed", FEED_URL), ("page", PAGE_URL))}
        for name, future in pending.items():
            try:
                body, headers = future.result()
                metadata[name] = cache_metadata(headers)
                if name == "feed":
                    feed = parse_feed(json.loads(body), expected)
                else:
                    page = parse_page(body, expected)
            except (FetchError, ValueError, TypeError, KeyError, AttributeError) as exc:
                errors[name] = str(exc) if isinstance(exc, FetchError) else f"Invalid {name} content ({type(exc).__name__})"
                print(f"::warning::{name}: {errors[name]}")
    now = utcnow()
    if args.command == "probe":
        print(json.dumps({"feed_ok": feed is not None, "page_ok": page is not None,
                          "screenings": len(feed or {}), "targets": {pid: (feed or {}).get(pid) for pid in TARGETS},
                          "page_rush": page, "cache": metadata, "errors": errors}, indent=2))
        return 0 if feed is not None and page is not None else 1
    # Seed only target identities so a page rush announcement works during a feed outage.
    if feed is None:
        for pid in TARGETS:
            state["screenings"].setdefault(pid, fallback_record(pid))
    events = observe(state, feed, page, errors, metadata, now)
    trigger = "automatic" if automatic else "manual"
    state["runs"][-1].update(trigger=trigger, run_id=env.get("GITHUB_RUN_ID"))
    if automatic:
        state["last_automatic_poll"] = stamp(now)
    store.save(state, events)  # Durable outbox before any notification side effect.
    deliver(state, store, now, env)
    # A manual check proves source access, not recovery of the automatic timer.
    # Only automatic cloud runs may clear a scheduler outage.
    if env.get("GITHUB_ACTIONS") != "true" or automatic:
        send_health(state, env)
    store.save(state)
    for key, value in state["configuration"].items():
        if not value:
            print(f"::warning::{key}: setup required")
    print(f"Observed {len(feed or {})} screenings; {len(events)} history changes. Feed={'ok' if feed is not None else 'failed'}, page={'ok' if page is not None else 'failed'}.")
    # A daily report also makes the first 24 hours of coverage reviewable.
    report_day = now.astimezone(ET).date().isoformat()
    if state.get("report_day") != report_day:
        history = store.folder / "changes.jsonl"
        all_events = [json.loads(line) for line in history.read_text().splitlines()] if history.exists() else []
        (store.folder / "report.md").write_text(report(state, all_events))
        state["report_day"] = report_day
        store.save(state)
    if not state.get("first_day_review_at") and now >= date(state["started_at"]) + timedelta(hours=24):
        history = store.folder / "changes.jsonl"
        all_events = [json.loads(line) for line in history.read_text().splitlines()] if history.exists() else []
        (store.folder / "first24hours.md").write_text(report(state, all_events))
        state["first_day_review_at"] = stamp(now)
        store.save(state)
    return 0 if feed is not None and page is not None and not state["notification_failures"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FetchError, ValueError, subprocess.CalledProcessError) as exc:
        # Never echo subprocess arguments, response bodies, or secret URLs.
        print(f"::error::Monitor operation failed ({type(exc).__name__}); inspect component status or repository permissions.")
        sys.exit(1)
