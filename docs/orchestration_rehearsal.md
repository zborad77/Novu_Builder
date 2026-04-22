# Orchestration Rehearsal Checklist

Tento checklist je urceny pro release hardening orchestrace a provozni overeni recoverability.

- [ ] restart worker during running analysis
- [ ] Redis flush during queued jobs
- [ ] duplicate command dispatch
- [ ] reconnect client mid-flow
- [ ] export stuck -> recovery
- [ ] quote recalculation retry idempotency
