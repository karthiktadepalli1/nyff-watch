# NYFF: quick operating guide

**Goal:** one ticket to any of the four *All of a Sudden* screenings.

## When an alert arrives

- **Possible ticket release:** open its purchase link promptly and look for one seat. The festival's availability indicator can lag checkout.
- **RUSH:** follow the published in-person sales window. Current guidance: $15, sales one hour before showtime; aim to arrive 90 minutes before.
- **Health alert:** open [monitor status](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml). One combined alert covers source failures and stopped scheduling. Healthchecks sends one recovery when successful automatic checking resumes. Manual checks do not announce scheduler recovery.

| Screening (Eastern) | Venue | Buy one ticket |
|---|---|---|
| Oct 1, 5 p.m. | Alice Tully Hall | [Checkout](https://purchase.filmlinc.org/84110/84274) |
| Oct 2, 2 p.m. | Alice Tully Hall | [Checkout](https://purchase.filmlinc.org/84110/84281) |
| Oct 4, 7:30 p.m. | Francesca Beale Theater | [Checkout](https://purchase.filmlinc.org/84110/84158) |
| Oct 9, 12:30 p.m. | Walter Reade Theater | [Checkout](https://purchase.filmlinc.org/84110/84159) |

## After buying a ticket

Open [monitor controls](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml), select **Run workflow**, choose **stop**, and confirm **Run workflow**. This records completion, pauses both health checks, and disables the monitor and its timer. Automatic expiry is October 9 at 12:30 p.m. Eastern; the first check at or after that time performs shutdown.

The same menu offers **poll** (check now), **test-alert** (phone and email test), and **report** (refresh timing analysis).

## Status and history

- [Latest runs and their summaries](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/watch.yml)
- [Automatic timer](https://github.com/karthiktadepalli1/nyff-watch/actions/workflows/timer.yml): **Waiting** is normal during each five-minute delay. If it has stopped unexpectedly, choose **Run workflow** once to restart it.
- [Festival-wide release timing report](https://github.com/karthiktadepalli1/nyff-watch/blob/data/report.md)
- [Saved observations](https://github.com/karthiktadepalli1/nyff-watch/tree/data)
- [Healthchecks account](https://healthchecks.io/): choose **NYFF 2026**.

Each timer waits five minutes, then queues a check of all four screenings and the next timer. Allow additional time for GitHub runner startup and festival caches. The run summary shows **Last automatic check**. Phone pushes are independent of the five-email daily allowance. The monitor continues in the cloud when your computer is asleep.

[Full setup and validation notes](README.md) · [Official rush guidance](https://www.filmlinc.org/how-to-nyff-guide/)
