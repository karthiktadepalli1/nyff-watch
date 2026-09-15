import base64
import json
import unittest
from unittest.mock import patch

import timer as t
import watch as w

NOW = w.date("2026-09-15T20:00:00Z")


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.state = w.initial_state()
        self.created = "2026-09-15T19:54:59Z"
        self.private = False
        self.dispatched = []
        self.active_runs = []
        self.fail_check = False
        self.env = {"GH_TOKEN": "unit-test-token", "GITHUB_RUN_ID": "123"}

    def request(self, url, *, payload=None, **kwargs):
        suffix = url.split(w.REPOSITORY, 1)[1]
        self.assertNotEqual(suffix, "/", "GitHub repository endpoint must not have a trailing slash")
        path = suffix.removeprefix("/")
        if path.endswith("/dispatches"):
            self.dispatched.append((path, payload))
            if self.fail_check and "watch.yml" in path:
                raise w.FetchError("Service unavailable")
            return "", {}
        values = {
            "actions/runs/123": {"created_at": self.created},
            "": {"private": self.private},
            "contents/state.json?ref=data": {"content": base64.b64encode(json.dumps(self.state).encode()).decode()},
            "actions/workflows/timer.yml/runs?per_page=10": {"workflow_runs": self.active_runs},
        }
        return json.dumps(values[path]), {}

    def run_tick(self, ensure=False):
        with patch.object(t, "request", side_effect=self.request), patch.object(t, "utcnow", return_value=NOW), patch("builtins.print"):
            t.run_timer(self.env, ensure=ensure)

    def test_tick_dispatches_check_then_next_wait(self):
        self.run_tick()
        self.assertEqual([x[0] for x in self.dispatched], ["actions/workflows/watch.yml/dispatches", "actions/workflows/timer.yml/dispatches"])
        self.assertEqual(self.dispatched[0][1]["inputs"]["operation"], "auto")

    def test_missing_wait_timer_cannot_create_rapid_loop(self):
        self.created = "2026-09-15T19:59:00Z"
        with self.assertRaises(ValueError):
            self.run_tick()
        self.assertEqual(self.dispatched, [])

    def test_private_repository_cannot_start_paid_loop(self):
        self.private = True
        with self.assertRaises(ValueError):
            self.run_tick()
        self.assertEqual(self.dispatched, [])

    def test_stopped_monitor_ends_chain(self):
        self.state["stopped"] = True
        self.state["shutdown_complete"] = True
        self.run_tick()
        self.assertEqual(self.dispatched, [])

    def test_failed_stop_cleanup_is_retried(self):
        self.state["stopped"] = True
        self.run_tick()
        self.assertEqual(len(self.dispatched), 2)
        self.assertIn("watch.yml", self.dispatched[0][0])
        self.assertIn("timer.yml", self.dispatched[1][0])

    def test_expiry_requests_cleanup_with_retry_timer(self):
        for pid in w.TARGETS:
            self.state["screenings"][pid] = {"start": "2026-09-15T19:59:00Z"}
        self.run_tick()
        self.assertEqual(len(self.dispatched), 2)
        self.assertIn("watch.yml", self.dispatched[0][0])

    def test_failed_check_dispatch_still_schedules_next_attempt(self):
        self.fail_check = True
        with self.assertRaises(w.FetchError):
            self.run_tick()
        self.assertIn("timer.yml", self.dispatched[-1][0])

    def test_backup_keeps_existing_timer(self):
        self.active_runs = [{"status": "waiting"}]
        self.run_tick(ensure=True)
        self.assertEqual(self.dispatched, [])

    def test_backup_restarts_missing_timer(self):
        self.active_runs = [{"status": "completed"}]
        self.run_tick(ensure=True)
        self.assertEqual([x[0] for x in self.dispatched], ["actions/workflows/timer.yml/dispatches"])
