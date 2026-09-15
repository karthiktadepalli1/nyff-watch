# Deployment checks — September 15, 2026

## Verified

- **Cloud access:** GitHub successfully parsed 305 festival screenings and all four target screening controls. All four targets were standby, with no observed RUSH designation. [Configured cloud check](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35008600552).
- **Persistence:** successive cloud runs preserved observations, generated the report, and suppressed repeated unchanged alerts.
- **Phone and email:** the user subscribed on their phone and confirmed that both channels received the fresh test. [Delivery test](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35009231642).
- **Independent health:** both production checks accepted cloud check-ins, each with a five-minute period and 25-minute grace. A separate test check detected two minutes of silence, recovered, accepted an explicit failure signal, recovered again, and was paused. Healthchecks reported successful email and ntfy deliveries. The shorter test threshold exercised the same missed-check mechanism while production retained its 30-minute threshold.
- **Regression checks:** 30 tests passed locally and on GitHub, covering availability for each of the four target IDs, rush sources, failures, retries, persistence, shutdown, and UTC email-allowance reset. [Tests](https://github.com/karthiktadepalli1/nyff-watch/actions/runs/35009712842).
- **Secrets:** all six required secrets are configured in GitHub. Public data stores configuration flags and delivery receipts.

## Still to observe

- **Scheduled execution:** the workflow is enabled, with the requested five-minute schedule. Initial manual checks succeeded while the first scheduled event was delayed. Treat regular automatic polling as unverified until `schedule` runs appear in the [run list](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml).
- **First 24 hours:** the monitor automatically saves `first24hours.md` after a full day. Review the polling gaps and source failures in that report.
- **Real rush positive:** the promotion mapping was verified against NYFF's display code and existing Q&A records. Rush-positive fixtures pass; a real NYFF RUSH designation remains the final live positive test.
- **Mac asleep:** cloud delivery and phone receipt are confirmed; the laptop's sleep state was not independently observed.
- **Shutdown:** automated tests cover manual and automatic shutdown, and the live pause API was exercised on the isolated test check. A full production shutdown was not used during deployment.
