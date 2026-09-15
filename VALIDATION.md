# Deployment checks — September 15, 2026

## Health-email investigation

At 4:05 p.m. Eastern, GitHub still had no scheduled runs. The last successful manual poll was at 2:48 p.m. Both original health checks therefore alerted for the same scheduler outage after 30 minutes. Setup had also generated failure/recovery messages from an isolated test check, which is paused. Ongoing reminders were already off.

Health notification routing now uses one combined monitor check. The page check remains a silent diagnostic. Periodic account reports are off, and manual cloud checks no longer send scheduler-recovery check-ins.

## Automatic timer repair

The repository and workflow were active and manual cloud checks succeeded, but GitHub had delivered no native `schedule` events. A GitHub environment wait timer now provides the recurring trigger: five minutes of server-side waiting, then dispatch the monitor and the next timer. The native schedule remains a backup. This changes the cadence from fixed clock minutes to approximately five minutes plus queue/startup time.

The `nyff-five-minute-timer` environment was verified with a five-minute delay and no required reviewers. The corrected timer was started once at 20:54:17 UTC. It completed two successive automatic checks **5 minutes 11 seconds apart** and queued the third timer. GitHub identifies the successor's triggering actor as `github-actions[bot]`; no local action was needed between cycles.

| Automatic observation (Eastern) | Result | Evidence |
|---|---|---|
| 4:59:38 p.m. | Feed and page succeeded; all four targets standby | [First automatic check](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35022945357) |
| 5:04:49 p.m. | Feed and page succeeded; all four targets standby | [Second automatic check](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35023474895) |

The saved state records both automatic run IDs, zero component failures, and zero pending alerts. Healthchecks showed **up** after each cycle. The [third timer](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35023476542) was waiting for its next five-minute delay. The monitor deduplicates overlapping triggers and retries incomplete shutdown cleanup.

## Verified

- **Cloud access:** GitHub successfully parsed 305 festival screenings and all four target screening controls. All four targets were standby, with no observed RUSH designation. [Configured cloud check](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35008600552).
- **Persistence:** successive cloud runs preserved observations, generated the report, and suppressed repeated unchanged alerts.
- **Phone and email:** the user subscribed on their phone and confirmed that both channels received the fresh test. [Delivery test](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35009231642).
- **Independent health:** both production checks accepted cloud check-ins, each with a five-minute period and 25-minute grace. A separate test check detected two minutes of silence, recovered, accepted an explicit failure signal, recovered again, and was paused. Healthchecks reported successful email and ntfy deliveries. The shorter test threshold exercised the same missed-check mechanism while production retained its 30-minute threshold.
- **Regression checks:** 42 tests passed locally and on GitHub, covering availability for each of the four target IDs, rush sources, failures, retries, persistence, shutdown, UTC email-allowance reset, timer chaining, the minimum wait guard, private-repository protection, backup restoration, and duplicate automatic triggers. [Tests](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35022446078).
- **Secrets:** all six required secrets are configured in GitHub. Public data stores configuration flags and delivery receipts.

## Still to observe

- **Native schedule:** no native `schedule` event has been observed. Automatic operation is verified through timer-triggered `workflow_dispatch` runs; the native schedule remains a backup.
- **First 24 hours:** the monitor automatically saves `first24hours.md` after a full day. Review the polling gaps and source failures in that report.
- **Real rush positive:** the promotion mapping was verified against NYFF's display code and existing Q&A records. Rush-positive fixtures pass; a real NYFF RUSH designation remains the final live positive test.
- **Mac asleep:** cloud delivery and phone receipt are confirmed; the laptop's sleep state was not independently observed.
- **Shutdown:** automated tests cover manual and automatic shutdown, and the live pause API was exercised on the isolated test check. A full production shutdown was not used during deployment.
