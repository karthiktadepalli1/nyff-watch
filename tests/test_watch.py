import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import urllib.error
from datetime import timedelta
from unittest.mock import patch

import watch as w

NOW = w.date("2026-09-15T17:00:00+00:00")
FILM_IDS = w.PROGRAMS["all-of-a-sudden"]["ids"]
LECTURE = "amos-vogel-lecture-hamaguchi"


def feed():
    programs = []
    for slug, program in w.PROGRAMS.items():
        shows = []
        for pid in w.TARGETS:
            if pid not in program["ids"]:
                continue
            start, venue = w.TARGETS[pid]
            shows.append({"id": pid, "dateTimeET": start, "venue": venue, "status": "standby",
                          "available": False, "noStandby": False,
                          "ticketsUrl": w.fallback_record(pid)["url"]})
        programs.append({"title": program["title"], "slug": slug,
                         "eventDetails" if '/events/' in program['page'] else "filmDetails": {"specialEvents": []},
                         "showtimes": shows})
    return {"slug": "nyff2026", "filmsWithShowtimes": programs}


def records():
    return w.parse_feed(feed(), set(w.TARGETS))


def page(rush=None, slug="all-of-a-sudden"):
    program = w.PROGRAMS[slug]
    return f"<html><body><h1>{program['title']}</h1><nav>Rush tickets</nav>" + "".join(
        f'<button data-performance-id="{pid}"><div><span>5:00 PM</span><span>{"RUSH" if pid == rush else "Q&A"}</span></div></button>'
        for pid in w.TARGETS if pid in program["ids"]) + "</body></html>"


def fetch_fixture(url, **kwargs):
    if url == w.FEED_URL:
        return json.dumps(feed()), {}
    slug = next(slug for slug, program in w.PROGRAMS.items() if program["page"] == url)
    return page(slug=slug), {}


def observe(state, data=None, html_rush=None, now=NOW):
    return w.observe(state, records() if data is None else data,
                     {pid: pid == html_rush for pid in w.TARGETS}, {}, {}, now)


class ParsingTests(unittest.TestCase):
    def test_promotion_ids_array_and_comma_strings(self):
        for value in (["84274", "84281"], "84274, 84281", ["84274,84281"]):
            payload = feed()
            payload["filmsWithShowtimes"][0]["filmDetails"]["specialEvents"] = [
                {"tessituraId": value, "promoShort": ["rush"], "promoTooltip": "Box office"}]
            result = w.parse_feed(payload, set(w.TARGETS))
            self.assertTrue(result["84274"]["rush"])
            self.assertTrue(result["84281"]["rush"])
            self.assertFalse(result["84158"]["rush"])

    def test_promotion_matches_site_precedence(self):
        payload = feed()
        payload["filmsWithShowtimes"][0]["filmDetails"]["specialEvents"] = [
            {"tessituraId": "84274", "promoShort": ["rush"]},
            {"tessituraId": "84274", "promoShort": ["qa", "rush"]}]
        self.assertFalse(w.parse_feed(payload, set(w.TARGETS))["84274"]["rush"])

    def test_page_ignores_generic_navigation_and_script_text(self):
        body = page() + '<script>"rush"; "data-performance-id=84274"</script>'
        self.assertFalse(any(w.parse_page(body, FILM_IDS).values()))

    def test_page_deduplicates_mobile_desktop(self):
        body = page("84274") + '<button data-performance-id="84274"><span>RUSH</span></button>'
        self.assertEqual(sum(w.parse_page(body, FILM_IDS).values()), 1)

    def test_incomplete_page_and_challenge_fail(self):
        for body in ("<html>Just a moment</html>", "<h1>All of a Sudden</h1>"):
            with self.assertRaises(ValueError):
                w.parse_page(body, FILM_IDS)

    def test_missing_target_and_wrong_film_fail(self):
        payload = feed()
        payload["filmsWithShowtimes"][0]["showtimes"].pop()
        with self.assertRaises(ValueError):
            w.parse_feed(payload, set(w.TARGETS))
        payload = feed()
        payload["filmsWithShowtimes"][0]["slug"] = "different-film"
        with self.assertRaises(ValueError):
            w.parse_feed(payload, set(w.TARGETS))

    def test_expired_targets_may_disappear(self):
        payload = feed()
        for program in payload["filmsWithShowtimes"]:
            program["showtimes"] = []
        self.assertEqual(w.parse_feed(payload, set()), {})

    def test_lecture_identity_link_and_event_rush_promotion(self):
        payload = feed()
        lecture = payload['filmsWithShowtimes'][1]
        lecture['eventDetails']['specialEvents'] = [
            {'tessituraId': ['84484'], 'promoShort': ['rush'], 'promoTooltip': 'Lecture rush'}]
        result = w.parse_feed(payload, set(w.TARGETS))['84484']
        self.assertTrue(result['rush'])
        self.assertEqual(result['rush_text'], 'Lecture rush')
        self.assertEqual(result['url'], 'https://purchase.filmlinc.org/84483/84484')
        self.assertIn('Vogel', result['film'])
        lecture['slug'] = 'another-lecture'
        with self.assertRaises(ValueError):
            w.parse_feed(payload, set(w.TARGETS))

    def test_lecture_page_requires_its_own_title_and_screening(self):
        title = w.PROGRAMS[LECTURE]['title']
        self.assertEqual(w.parse_page(page(slug=LECTURE), {'84484'}, title), {'84484': False})
        self.assertEqual(w.parse_page(page('84484', LECTURE), {'84484'}, title), {'84484': True})
        for body in (page(), '<h1>' + title + '</h1>'):
            with self.assertRaises(ValueError):
                w.parse_page(body, {'84484'}, title)

    def test_lecture_page_is_retired_after_its_start(self):
        expected = w.expected_ids(w.initial_state(), w.date('2026-10-03T18:00:00Z'))
        with patch.object(w, 'request', side_effect=fetch_fixture) as request:
            _, pages, errors, _ = w.fetch_sources(expected)
        self.assertNotIn(w.PROGRAMS[LECTURE]['page'], [call.args[0] for call in request.call_args_list])
        self.assertNotIn('84484', pages)
        self.assertFalse(errors)

    def test_possible_love_targets_only_the_two_director_qa_screenings(self):
        self.assertEqual(w.PROGRAMS['possible-love']['ids'], {'84409', '84410'})
        payload = feed()
        film = next(p for p in payload['filmsWithShowtimes'] if p['slug'] == 'possible-love')
        film['showtimes'].append(dict(film['showtimes'][0], id='84411', status='available',
                                     ticketsUrl='https://purchase.filmlinc.org/84136/84411'))
        data = w.parse_feed(payload, set(w.TARGETS))
        state = w.initial_state()
        w.observe(state, data, {}, {}, {}, NOW)
        self.assertIn('84411', state['screenings'])
        self.assertFalse(state['outbox'])
        html = page(slug='possible-love') + '<button data-performance-id="84411">RUSH</button>'
        self.assertEqual(w.parse_page(html, {'84409', '84410'}, 'Possible Love'),
                         {'84409': False, '84410': False})

    def test_lee_talk_uses_its_own_page_and_purchase_link(self):
        program = w.PROGRAMS['talk-lee-chang-dong']
        self.assertEqual(w.fallback_record('84480')['url'], 'https://purchase.filmlinc.org/84479/84480')
        self.assertEqual(w.parse_page(page(slug='talk-lee-chang-dong'), {'84480'}, program['title']),
                         {'84480': False})


class ObservationTests(unittest.TestCase):
    def test_any_target_can_trigger_a_ticket_alert(self):
        for pid in w.TARGETS:
            with self.subTest(performance_id=pid):
                state, data = w.initial_state(), records()
                observe(state, data)
                data[pid]["status"] = "available"
                observe(state, data, now=NOW + timedelta(minutes=5))
                alerts = [a for a in state["outbox"] if a["kind"] == "ticket"]
                self.assertEqual([a["performance_id"] for a in alerts], [pid])
                self.assertEqual(alerts[0]["click"], data[pid]["url"])

    def test_newly_watched_lecture_alerts_if_already_open_in_catalogue(self):
        state, data = w.initial_state(), records()
        observe(state, data)
        state.pop('watched_ids')  # State from the four-screening deployment.
        state['screenings']['84484'].update(status='available', rush=True)
        data['84484'].update(status='available', rush=True)
        observe(state, data, now=NOW + timedelta(minutes=5))
        self.assertEqual([(a['kind'], a['performance_id']) for a in state['outbox']],
                         [('ticket', '84484'), ('rush', '84484')])
        self.assertTrue(all('Vogel' in a['message'] for a in state['outbox']))
        observe(state, data, now=NOW + timedelta(minutes=10))
        self.assertEqual(len(state['outbox']), 2)

    def test_failed_lecture_page_keeps_film_rush_detection_and_records_failure(self):
        def fetch(url, **kwargs):
            if url == w.PROGRAMS[LECTURE]['page']:
                raise w.FetchError('HTTP 503 from www.filmlinc.org')
            if url == w.PAGE_URL:
                return page('84274'), {}
            return fetch_fixture(url)
        with patch.object(w, 'request', side_effect=fetch), patch('builtins.print'):
            data, pages, errors, metadata = w.fetch_sources(set(w.TARGETS))
        state = w.initial_state()
        state['page_rush']['84484'] = {'rush': False, 'observed_at': w.stamp(NOW)}
        w.observe(state, data, pages, errors, metadata, NOW)
        self.assertEqual(state['components']['page']['failures'], 1)
        self.assertIn(LECTURE, state['components']['page']['error'])
        self.assertFalse(state['runs'][-1]['page'])
        self.assertEqual([a['performance_id'] for a in state['outbox']], ['84274'])
        self.assertEqual(state['page_rush']['84484']['observed_at'], w.stamp(NOW))

    def test_lecture_page_rush_survives_feed_and_film_page_failures(self):
        def fetch(url, **kwargs):
            if url == w.PROGRAMS[LECTURE]['page']:
                return page('84484', LECTURE), {}
            raise w.FetchError('HTTP 503')
        with patch.object(w, 'request', side_effect=fetch), patch('builtins.print'):
            data, pages, errors, metadata = w.fetch_sources(set(w.TARGETS))
        state = w.initial_state()
        state['screenings'] = {pid: w.fallback_record(pid) for pid in w.TARGETS}
        w.observe(state, data, pages, errors, metadata, NOW)
        alert = state['outbox'][0]
        self.assertEqual(alert['performance_id'], '84484')
        self.assertEqual(alert['click'], 'https://purchase.filmlinc.org/84483/84484')
        self.assertIn('Vogel', alert['message'])

    def test_first_opening_repeat_and_reopening(self):
        state, data = w.initial_state(), records()
        data["84274"]["status"] = "limited"
        observe(state, data)
        self.assertEqual(len(state["outbox"]), 1)
        observe(state, data, now=NOW + timedelta(minutes=5))
        self.assertEqual(len(state["outbox"]), 1)
        data["84274"]["status"] = "standby"
        observe(state, data, now=NOW + timedelta(minutes=10))
        data["84274"]["status"] = "available"
        observe(state, data, now=NOW + timedelta(minutes=15))
        self.assertEqual(len(state["outbox"]), 2)

    def test_both_rush_sources_produce_one_alert(self):
        state, data = w.initial_state(), records()
        data["84274"]["rush"] = True
        observe(state, data, "84274")
        self.assertEqual(len(state["outbox"]), 1)
        self.assertEqual(state["outbox"][0]["kind"], "rush")
        self.assertIn("In-person purchase", state["outbox"][0]["message"])

    def test_failed_feed_does_not_reset_status(self):
        state, data = w.initial_state(), records()
        data["84274"]["status"] = "available"
        observe(state, data)
        old = copy.deepcopy(state["screenings"])
        w.observe(state, None, None, {"feed": "HTTP 503", "page": "HTTP 403"}, {}, NOW + timedelta(minutes=5))
        self.assertEqual(state["screenings"], old)
        observe(state, data, now=NOW + timedelta(minutes=10))
        self.assertEqual(len(state["outbox"]), 1)

    def test_page_rush_during_feed_failure(self):
        state = w.initial_state()
        state["screenings"] = {pid: w.fallback_record(pid) for pid in w.TARGETS}
        w.observe(state, None, {"84274": True}, {"feed": "HTTP 503"}, {}, NOW)
        self.assertEqual(state["outbox"][0]["kind"], "rush")

    def test_elapsed_show_never_alerts(self):
        state, data = w.initial_state(), records()
        data["84274"].update(status="available", rush=True)
        observe(state, data, "84274", w.date("2026-10-02T00:00:00Z"))
        self.assertEqual(state["outbox"], [])

    def test_schedule_and_standby_change_alert(self):
        state, data = w.initial_state(), records()
        observe(state, data)
        data["84274"].update(venue="Walter Reade Theater", no_standby=True)
        observe(state, data, now=NOW + timedelta(minutes=5))
        self.assertEqual(state["outbox"][0]["kind"], "update")

    def test_other_film_logged_without_ticket_alert(self):
        state, data = w.initial_state(), records()
        observe(state, data)
        data["90000"] = dict(data["84274"], id="90000", film="Another film", status="available")
        events = observe(state, data, now=NOW + timedelta(minutes=5))
        self.assertEqual(events[0]["kind"], "catalogue_addition")
        self.assertEqual(state["outbox"], [])

    def test_report_groups_batch_and_excludes_initial_inventory(self):
        state, data = w.initial_state(), records()
        events = observe(state, data)
        data["84274"]["status"] = data["84281"]["status"] = "available"
        events += observe(state, data, now=NOW + timedelta(minutes=5))
        output = w.report(state, events)
        self.assertIn("**2** across **1 batches**", output)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = w.Store(self.temp.name)
        self.state, data = w.initial_state(), records()
        data["84274"]["status"] = "available"
        observe(self.state, data)
        self.store.save(self.state)
        self.env = {"NTFY_TOPIC": "unit-test-topic", "NTFY_TOKEN": "unit-test-token", "ALERT_EMAIL": "test@example.invalid"}

    def test_email_failure_does_not_repeat_successful_push(self):
        calls = []
        def fail_email(alert, channel, env):
            calls.append(channel)
            if channel == "email":
                raise w.FetchError("HTTP 503 from ntfy.sh")
        w.deliver(self.state, self.store, NOW, self.env, fail_email)
        reloaded = self.store.load()
        w.deliver(reloaded, self.store, NOW + timedelta(minutes=5), self.env, lambda a, c, e: calls.append(c))
        self.assertEqual(calls, ["push", "email", "email"])
        self.assertEqual(reloaded["outbox"][0]["email"], "sent")

    def test_reloaded_success_does_not_repeat(self):
        calls = []
        w.deliver(self.state, self.store, NOW, self.env, lambda a, c, e: calls.append(c))
        w.deliver(self.store.load(), self.store, NOW + timedelta(minutes=5), self.env, lambda a, c, e: calls.append(c))
        self.assertEqual(calls, ["push", "email"])

    def test_email_budget_leaves_push_working(self):
        self.state["email_budget"] = {"day": NOW.date().isoformat(), "attempts": 5}
        calls = []
        w.deliver(self.state, self.store, NOW, self.env, lambda a, c, e: calls.append(c))
        self.assertEqual(calls, ["push"])
        self.assertEqual(self.state["outbox"][0]["email"], "pending")

    def test_closed_opening_is_not_sent_late(self):
        self.state["screenings"]["84274"]["status"] = "standby"
        calls = []
        w.deliver(self.state, self.store, NOW, self.env, lambda a, c, e: calls.append(c))
        self.assertEqual(calls, [])
        self.assertEqual(self.state["outbox"][0]["push"], "expired")

    def test_email_allowance_resets_at_utc_midnight(self):
        before = w.date("2026-09-15T23:59:00Z")
        self.state["outbox"] = []
        w.add_alert(self.state, "test", self.state["screenings"]["84274"], before)
        self.state["email_budget"] = {"day": "2026-09-15", "attempts": 5}
        calls = []
        w.deliver(self.state, self.store, before, self.env, lambda a, c, e: calls.append(c))
        self.assertEqual(calls, ["push"])
        w.deliver(self.state, self.store, before + timedelta(minutes=2), self.env,
                  lambda a, c, e: calls.append(c))
        self.assertEqual(calls, ["push", "email"])
        self.assertEqual(self.state["email_budget"]["attempts"], 1)

    def test_email_secondary_topic_avoids_duplicate_phone_push(self):
        with patch.object(w, "request") as request:
            w.notify(self.state["outbox"][0], "email", self.env)
        payload = request.call_args.kwargs["payload"]
        self.assertEqual(payload["topic"], "unit-test-topic-email")

    def test_credentials_never_enter_state(self):
        w.deliver(self.state, self.store, NOW, self.env, lambda *args: None)
        content = (Path(self.temp.name) / "state.json").read_text()
        for secret in self.env.values():
            self.assertNotIn(secret, content)


class HealthAndStopTests(unittest.TestCase):
    def setUp(self):
        self.env = {"HC_FEED_URL": "https://hc-ping.com/11111111-1111-4111-8111-111111111111",
                    "HC_PAGE_URL": "https://hc-ping.com/22222222-2222-4222-8222-222222222222",
                    "HC_API_KEY": "unit-test-key"}

    def test_third_failure_then_single_recovery(self):
        state = w.initial_state()
        observe(state)
        with patch.object(w, "request", return_value=("", {})) as request:
            for n in range(3):
                w.component_result(state, "feed", NOW, "failure")
                w.send_health(state, self.env)
            failures = [c for c in request.call_args_list if c.args[0].endswith("/fail")]
            self.assertEqual(len(failures), 1)
            w.send_health(state, self.env)
            self.assertEqual(len([c for c in request.call_args_list if c.args[0].endswith("/fail")]), 1)
            w.component_result(state, "feed", NOW)
            w.send_health(state, self.env)
            self.assertEqual(state["components"]["feed"]["health_signal"], "up")

    def test_stop_pauses_both_before_disabling_workflow(self):
        with tempfile.TemporaryDirectory() as folder:
            store = w.Store(folder)
            state = w.initial_state()
            env = dict(self.env, GITHUB_ACTIONS="true", GH_TOKEN="unit-test-token")
            with patch.object(w, "request", return_value=("", {})) as request:
                w.stop_monitor(state, store, NOW, env, "test")
            paths = [c.args[0] for c in request.call_args_list]
            self.assertEqual(len(paths), 4)
            self.assertTrue(paths[0].endswith("/pause"))
            self.assertTrue(paths[1].endswith("/pause"))
            self.assertTrue(paths[2].endswith("timer.yml/disable"))
            self.assertTrue(paths[3].endswith("watch.yml/disable"))
            self.assertTrue(store.load()["stopped"])
            self.assertTrue(store.load()["shutdown_complete"])

    def test_failed_pause_preserves_stop_and_workflow_for_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            store, state = w.Store(folder), w.initial_state()
            with patch.object(w, "request", side_effect=w.FetchError("unavailable")) as request:
                with self.assertRaises(w.FetchError):
                    w.stop_monitor(state, store, NOW, self.env, "test")
            self.assertTrue(store.load()["stopped"])
            self.assertFalse(store.load().get("shutdown_complete", False))
            self.assertEqual(request.call_count, 1)

    def test_automatic_expiry_calls_stop_at_last_showtime(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('sys.argv', ['watch.py', 'poll', '--data', folder]), \
                 patch.object(w, 'utcnow', return_value=w.date('2026-10-09T16:30:00Z')), \
                 patch.object(w, 'stop_monitor') as stop, patch.object(w, 'request') as request:
                self.assertEqual(w.main(), 0)
                self.assertEqual(stop.call_args.args[-1], 'final screening started')
                request.assert_not_called()

    def test_notification_failure_sends_independent_health_failure(self):
        state = w.initial_state()
        observe(state)
        state['notification_failures'] = 3
        with patch.object(w, 'request', return_value=('', {})) as request:
            w.send_health(state, self.env)
        self.assertTrue(request.call_args_list[0].args[0].endswith('/fail'))

    def test_page_failure_triggers_aggregate_health_and_recovery_waits_for_both(self):
        state = w.initial_state()
        observe(state)
        state['components']['page']['failures'] = 3
        with patch.object(w, 'request', return_value=('', {})) as request:
            w.send_health(state, self.env)
            self.assertEqual(request.call_args_list[0].args[0], self.env['HC_FEED_URL'] + '/fail')
            request.reset_mock()
            # A changing source of failure must not generate a false recovery.
            state['components']['page']['failures'] = 0
            state['components']['feed']['failures'] = 3
            w.send_health(state, self.env)
            self.assertNotIn(self.env['HC_FEED_URL'], [c.args[0] for c in request.call_args_list])
            request.reset_mock()
            state['components']['feed']['failures'] = 0
            w.send_health(state, self.env)
            self.assertEqual(request.call_args_list[0].args[0], self.env['HC_FEED_URL'])

    def test_manual_cloud_poll_does_not_signal_scheduler_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('sys.argv', ['watch.py', 'poll', '--data', folder]), \
                 patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}, clear=True), \
                 patch.object(w, 'utcnow', return_value=NOW), patch.object(w, 'request', side_effect=fetch_fixture), \
                 patch.object(w, 'send_health') as health, patch('builtins.print'):
                self.assertEqual(w.main(), 0)
                health.assert_not_called()

    def test_timer_check_updates_health_and_deduplicates_automatic_triggers(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('sys.argv', ['watch.py', 'auto', '--data', folder]), \
                 patch.dict(os.environ, {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch'}, clear=True), \
                 patch.object(w, 'utcnow', return_value=NOW), patch.object(w, 'request', side_effect=fetch_fixture) as network, \
                 patch.object(w, 'send_health') as health, patch('builtins.print'):
                self.assertEqual(w.main(), 0)
                health.assert_called_once()
                self.assertEqual(w.Store(folder).load()['last_automatic_poll'], w.stamp(NOW))
                self.assertEqual(w.Store(folder).load()['runs'][-1]['trigger'], 'automatic')
                network.reset_mock()
                health.reset_mock()
                self.assertEqual(w.main(), 0)
                network.assert_not_called()
                health.assert_not_called()

    def test_network_errors_retry_twice_and_redact_secret_path(self):
        secret_url = 'https://hc-ping.com/private-path'
        error = urllib.error.HTTPError(secret_url, 503, 'busy', {}, None)
        with patch.object(w.urllib.request, 'urlopen', side_effect=error) as fetch, \
             patch.object(w.time, 'sleep'):
            with self.assertRaises(w.FetchError) as raised:
                w.request(secret_url)
        self.assertEqual(fetch.call_count, 3)
        self.assertNotIn('private-path', str(raised.exception))

    def test_cloud_access_denial_is_not_retried_as_transient(self):
        error = urllib.error.HTTPError(w.PAGE_URL, 403, 'blocked', {}, None)
        with patch.object(w.urllib.request, 'urlopen', side_effect=error) as fetch:
            with self.assertRaises(w.FetchError):
                w.request(w.PAGE_URL)
        self.assertEqual(fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
