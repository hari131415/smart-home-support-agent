### Eval (full): FAIL

model `gemini-3.8-flash`, prompt `v3` (277c3bdc09dd)

| metric | value |
|---|---|
| answer accuracy | 29.2% |
| handoff recall | 100.0% |
| overall | 43.3% |
| cost | $0.000 |
| p95 latency | 27415 ms |

| category | pass rate |
|---|---|
| access_control | 100% |
| device_status | 29% |
| escalation | 100% |
| injection | 100% |
| manual_qa | 29% |
| safety | 100% |

**Failing thresholds:**
- answer accuracy 0.2917 < 0.85
