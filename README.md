# NYFF ticket monitor

Watch for one ticket to *All of a Sudden* at NYFF64. Checks are scheduled in GitHub every five minutes, at minutes 2, 7, 12, and so on. Phone push, email, and independent health alerts are configured. Complete the phone subscription and delivery checks before relying on alerts.

**[Monitor status and controls](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml)** · **[Release history](https://github.com/karthiktadepalli1/nyff-watch/tree/data)** · **[Timing report](https://github.com/karthiktadepalli1/nyff-watch/blob/data/report.md)**

[Quick operating guide](OPERATING.md) · [Deployment validation](VALIDATION.md)

## Screenings and purchase links

All times are Eastern. Each alert is a prompt to check checkout for one remaining seat.

| Screening | Venue | Purchase |
|---|---|---|
| Thursday, October 1, 5 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84110/84274) |
| Friday, October 2, 2 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84110/84281) |
| Sunday, October 4, 7:30 p.m. | Francesca Beale Theater | [Open checkout](https://purchase.filmlinc.org/84110/84158) |
| Friday, October 9, 12:30 p.m. | Walter Reade Theater | [Open checkout](https://purchase.filmlinc.org/84110/84159) |

## What runs

- **Tickets:** reads the official festival feed, matches the four performance IDs, and alerts on available/limited status. An initially open screening also alerts. A closure followed by reopening generates a new alert.
- **Rush:** reads screening-specific promotion metadata and independently inspects RUSH labels on the film page. Repeated desktop/mobile controls produce one result. The current site's promotion mapping is validated; the first live rush announcement provides a further real-world check.
- **History:** stores compact changes across all festival screenings on the `data` branch, including observation times, cache headers, availability, rush status, and screening details. A report is generated daily and on demand, with a saved `first24hours.md` report once the first full day has elapsed. New shows enter the dataset; alerts target the four screenings above.
- **Health:** one combined **NYFF monitor** check alerts after 30 minutes without a successful scheduled check-in, or three consecutive failures of the feed, film page, or delivery. The separate page check is a silent dashboard diagnostic. Both sources must recover before the combined check recovers. Manual polls do not clear a scheduler outage. Ongoing reminders and periodic email reports are off.
- **Completion:** `stop` records that a ticket was secured, pauses the configured health checks, and disables this workflow. Automatic expiry uses the last target's start time; the October 9 start also has a dedicated schedule entry. GitHub can delay scheduled runs.

Standard GitHub runners in this public repository, ntfy's free service, and Healthchecks.io's free plan are the intended $0 setup. GitHub scheduling and source caches can delay detection beyond five minutes. The run summary shows access failures and setup status explicitly.

## Account setup

### 1. Phone and email

1. Create/sign in to a free account at [ntfy](https://ntfy.sh/app). Verify your alert email in Account settings and create an access token for this monitor.
2. Install the ntfy app on your phone and allow notifications.
3. From this checkout run `python3 configure.py notifications`. It securely saves the token, email, and a generated random topic in GitHub Secrets. The displayed topic is the one to subscribe to in your phone app, using server `https://ntfy.sh`.
4. Subscribe only to the displayed topic. Email copies use a separate topic to prevent email retries creating duplicate phone pushes.
5. In **Monitor status and controls → Run workflow**, choose **test-alert**. Confirm both the phone push and email arrive, then test with the Mac asleep. The test is clearly labeled.

The monitor budgets at most five email attempts per UTC calendar day, matching ntfy's reset time. ntfy's own limits remain authoritative. Email failures are retried separately from successful pushes, while the opportunity remains relevant. Pending opportunities expire when they close, pass showtime, or become six hours old. A crash immediately after external delivery and before the success receipt is saved can produce a duplicate; completed deliveries are otherwise deduplicated.

### 2. Independent failure alerts

1. Create a free [Healthchecks.io](https://healthchecks.io/) account and a dedicated project named **NYFF**.
2. Add a verified email integration named **NYFF email**. Enable failure and recovery messages.
3. Add an **ntfy** integration named **NYFF phone**, using the generated topic, server `https://ntfy.sh`, and the monitor's ntfy access token. Enable both down and up notifications. This sends health alerts independently of GitHub. Keep the topic and token inside Healthchecks settings.
4. Create a read-write API key in the NYFF project's settings. Run `python3 configure.py health` and enter it at the hidden prompt. This configures the combined monitor check with both integrations and a silent page diagnostic, and saves the required secrets. In Account Settings → Email Reports, select **Off** and **Do not remind me**.
5. Confirm an automatic **schedule** run completes and both checks become healthy. A manual **poll** checks tickets but deliberately does not clear an automatic-scheduling outage. Use a silent isolated check for further failure tests; user-facing delivery was validated during setup.

Secrets used: `NTFY_TOPIC`, `NTFY_TOKEN`, `ALERT_EMAIL`, `HC_API_KEY`, `HC_FEED_URL`, `HC_PAGE_URL`. The dedicated Healthchecks project's API key permits automatic pause at completion.

## Everyday controls

Open **[Run workflow](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml)** and choose:

| Operation | Result |
|---|---|
| `poll` | Check now, record changes, send actionable alerts |
| `test-alert` | Send clearly labeled phone and email tests |
| `report` | Refresh the release timing report |
| `probe` | Test live feed/page access without updating observations or sending alerts |
| `stop` | Record success, pause health checks, and stop scheduling |

After purchasing one ticket, use **stop**. If pausing a health check fails, the stopped state is retained and subsequent runs retry cleanup before disabling the workflow.

## Rush and in-person action

Rush alerts indicate **in-person** admission at the venue, currently $15, subject to availability. Sales start one hour before the screening; aim to arrive 90 minutes beforehand. Regular standby remains a separate option; a three-hour arrival buffer is a planning estimate, with admission uncertain. Before screening day, ask Alice Tully's box office for one partial-view seat to October 1 or 2. The $250 Express Pass remains a fallback.

[Official NYFF guide](https://www.filmlinc.org/how-to-nyff-guide/) · [Ticket/pass rules](https://www.filmlinc.org/nyff/tickets-and-passes/) · [Film page](https://www.filmlinc.org/nyff2026/films/all-of-a-sudden/)

## Validation and development

`python3 -m unittest discover -s tests -v` runs offline tests for opening/reopening, rush parsing and deduplication, generic-text false positives, source failures, expiry, history batches, independent notification retries, email budgeting, secret exclusion, health recovery, and shutdown order. `python3 watch.py probe --data /tmp/nyff-probe` checks real access.

Runtime: Python 3.11+, standard library. Workflow-level concurrency serializes all controls. The data branch is checked out after the execution slot is acquired. Observations and pending alerts are committed before notification delivery; receipts are committed after delivery. GitHub's built-in token writes observations and disables the workflow at completion.

Before declaring full operation, check several scheduled runs, confirm phone/email delivery with the Mac asleep, verify independent missed-check and recovery notifications, and review the first 24 hours in the timing report. The first genuine rush label still needs validation when NYFF publishes it.
