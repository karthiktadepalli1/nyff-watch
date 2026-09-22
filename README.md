# NYFF ticket monitor

Watch for one-ticket openings at nine NYFF64 events: four *All of a Sudden* screenings, Hamaguchi's Amos Vogel Lecture, Lee Chang-dong's talk, the two *Possible Love* screenings with director Q&As, and *You Can See Everything* with Nathan Fielder and Lance Oppenheim's Q&A. A GitHub-hosted timer starts a check about every five minutes, plus runner startup time. Phone push, email, and independent health alerts are configured; phone and email delivery have been confirmed.

**[Monitor status and controls](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml)** · **[Release history](https://github.com/karthiktadepalli1/nyff-watch/tree/data)** · **[Timing report](https://github.com/karthiktadepalli1/nyff-watch/blob/data/report.md)**

[Quick operating guide](OPERATING.md) · [Deployment validation](VALIDATION.md)

## Screenings and purchase links

All times are Eastern. Each alert is a prompt to check checkout for one remaining seat.

| Event | Date and time | Venue | Purchase |
|---|---|---|---|
| Possible Love + Q&A with Lee Chang-dong and cast | September 27, 5:30 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84136/84409) |
| Possible Love + Q&A with Lee Chang-dong | September 28, 11:30 a.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84136/84410) |
| Talk: Lee Chang-dong | September 28, 4:45 p.m. | Francesca Beale Theater | [Open checkout](https://purchase.filmlinc.org/84479/84480) |
| You Can See Everything + Q&A with Nathan Fielder and Lance Oppenheim | September 30, 8 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84650/84652) |
| All of a Sudden | October 1, 5 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84110/84274) |
| All of a Sudden | October 2, 2 p.m. | Alice Tully Hall | [Open checkout](https://purchase.filmlinc.org/84110/84281) |
| Amos Vogel Lecture: Ryûsuke Hamaguchi | October 3, 1:30 p.m. | Walter Reade Theater | [Open checkout](https://purchase.filmlinc.org/84483/84484) |
| All of a Sudden | October 4, 7:30 p.m. | Francesca Beale Theater | [Open checkout](https://purchase.filmlinc.org/84110/84158) |
| All of a Sudden | October 9, 12:30 p.m. | Walter Reade Theater | [Open checkout](https://purchase.filmlinc.org/84110/84159) |

The two *Possible Love* performance IDs were matched to the official director Q&A promotion records on September 17. [Possible Love](https://www.filmlinc.org/nyff2026/films/possible-love/) · [Lee Chang-dong talk](https://www.filmlinc.org/nyff2026/events/talk-lee-chang-dong/) · [Hamaguchi lecture](https://www.filmlinc.org/nyff2026/events/amos-vogel-lecture-hamaguchi/)

## What runs

- **Tickets:** reads the official festival feed, matches the nine performance IDs, and alerts on available/limited status. An initially open event also alerts, including when newly added to the watch list after appearing in the festival history. A closure followed by reopening generates a new alert.
- **Rush:** reads screening-specific promotion metadata and independently inspects RUSH labels on each of the five program pages. Repeated desktop/mobile controls produce one result. The current site's promotion mapping is validated; the first live rush announcement provides a further real-world check.
- **History:** stores compact changes across all festival screenings on the `data` branch, including observation times, cache headers, availability, rush status, and screening details. A report is generated daily and on demand, with a saved `first24hours.md` report once the first full day has elapsed. New shows enter the dataset; alerts target the nine events above.
- **Health:** one combined **NYFF monitor** check alerts after 30 minutes without a successful automatic check-in, or three consecutive failures of the feed, program pages, or delivery. The separate page check is a silent dashboard diagnostic. Successful pages keep contributing rush signals when another page fails; all active pages must recover before the combined check recovers. Manual polls do not clear a scheduler outage. Ongoing reminders and periodic email reports are off.
- **Completion:** `stop` records that a ticket was secured, pauses the configured health checks, and disables both monitor and timer workflows. Automatic expiry uses the last target's start time; the next automatic check performs shutdown. The October 9 start also has a dedicated backup schedule entry.

Standard GitHub runners in this public repository, ntfy's free service, and Healthchecks.io's free plan are the intended $0 setup. GitHub queueing and source caches can delay detection beyond five minutes. The run summary shows the last automatic check, access failures, and setup status explicitly.

## Automatic timer

The [timer workflow](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/timer.yml) uses the `nyff-five-minute-timer` environment, configured with a **five-minute wait timer and no required reviewers**. After the delay, a short job dispatches a ticket check and its next timer run. Waiting happens in GitHub before allocating a runner. GitHub permits its built-in token to trigger `workflow_dispatch` events, so this needs no personal token or external scheduler. [Wait timers](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) · [Workflow triggering](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)

The original minute-2,7,12,… schedule remains as a backup. If it resumes, it can restore an interrupted timer. Automatic triggers less than four minutes apart are deduplicated. Each actual check reads the entire festival feed once and checks all nine target events, plus their five program pages. Each program page retires after its final watched event begins.

To start or restore the timer, open the timer workflow and choose **Run workflow** once. Its **Waiting** status is normal. The timer verifies that five minutes elapsed before dispatching; bypassing or removing the environment wait halts the chain. It also halts if the repository becomes private. When finished seeking tickets, use the monitor's **stop** control.

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
5. Confirm successive timer-triggered **auto** runs complete and both checks become healthy. A manual **poll** checks tickets but deliberately does not clear an automatic-scheduling outage. Use a silent isolated check for further failure tests; user-facing delivery was validated during setup.

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
| `auto` | Internal operation dispatched by the automatic timer |

When finished seeking tickets, use **stop** to end monitoring for all nine events. If pausing a health check fails, the stopped state is retained and subsequent runs retry cleanup before disabling both workflows.

## Rush and in-person action

Rush alerts indicate **in-person** admission at the venue, currently $15, subject to availability. Sales start one hour before the screening; aim to arrive 90 minutes beforehand. Regular standby remains a separate option; a three-hour arrival buffer is a planning estimate, with admission uncertain. Before screening day, ask Alice Tully's box office for one partial-view seat to October 1 or 2. The $250 Express Pass remains a fallback.

[Official NYFF guide](https://www.filmlinc.org/how-to-nyff-guide/) · [Ticket/pass rules](https://www.filmlinc.org/nyff/tickets-and-passes/) · [Film page](https://www.filmlinc.org/nyff2026/films/all-of-a-sudden/)

## Validation and development

`python3 -m unittest discover -s tests -v` runs offline tests for opening/reopening, rush parsing and deduplication, generic-text false positives, source failures, expiry, history batches, independent notification retries, email budgeting, secret exclusion, health recovery, and shutdown order. `python3 watch.py probe --data /tmp/nyff-probe` checks real access.

Runtime: Python 3.11+, standard library. Workflow-level concurrency serializes all controls. The data branch is checked out after the execution slot is acquired. Observations and pending alerts are committed before notification delivery; receipts are committed after delivery. GitHub's built-in token writes observations and disables both workflows at completion.

Before declaring full operation, check successive automatic runs, confirm phone/email delivery with the Mac asleep, verify independent missed-check and recovery notifications, and review the first 24 hours in the timing report. The first genuine rush label still needs validation when NYFF publishes it.
