# ORACLE — Monitoring policy

## What ORACLE is for

Monitoring public websites you own or have explicit permission to
monitor, for legitimate competitive research.

## Rules

1. **Authorization required.** Registering a URL requires
   `authorized=True` plus an `authorization_note` stating the basis
   (e.g. "own site", "client site, written permission 2026-11-01").
   Registration without it is refused by the code, not just by policy.
2. **Respect robots.txt** where applicable, site terms of service,
   and access controls.
3. **Respect rate limits.** Per-domain request caps are hard limits
   (default 2 requests/minute/host in the spec's worker contract;
   the demo uses a higher cap only against its own local fixtures).
   Never use ORACLE as a high-speed firehose.
4. **Never bypass** logins, paywalls, bot checks, CAPTCHAs, or other
   access restrictions. If a page requires access you do not have,
   do not monitor it.
5. **Never log** cookies or authorization headers. The fetcher sends
   none and stores none.
6. **Copyright.** Snapshots are stored for change comparison, not
   republication. Do not republish monitored content.
7. **Observation, not accusation.** ORACLE reports when a difference
   was observed, never when a site "changed" at an exact time.

## Takedown / contact

If you believe ORACLE is being used to monitor your site without
authorization, contact the repository owner with the monitored URL
and the date range. The owner will remove the URL from the registry
and delete its snapshots. A `docs/CONTACT.md` with a monitored
contact address should be added before any public deployment.
