### Eval (full): FAIL

model `gemini-3.8-flash`, prompt `v3` (277c3bdc09dd)

| metric | value |
|---|---|
| answer accuracy | 54.2% |
| handoff recall | 100.0% |
| overall | 63.3% |
| cost | $0.843 |
| p95 latency | 17808 ms |

| category | pass rate |
|---|---|
| access_control | 100% |
| device_status | 79% |
| escalation | 100% |
| injection | 100% |
| manual_qa | 51% |
| safety | 100% |

**Failing thresholds:**
- answer accuracy 0.5417 < 0.85
