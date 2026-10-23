# Agent evaluation: replay-fixed-of-live-2

- Mode: **replay**; model: `replay of live-2`; run: 2026-10-23 08:56 UTC.
- Recordings: `eval/recordings/live-2`. Gold answers computed from the graph when the run was scored.
- Question set: v1; pause between questions: 0.0 s.
- **Note:** Replay of live-2's recorded model turns with the fixes of 2026-10-23 (misrouted-answer recovery, 'claim' spelling, dash-normalised scorer, trimmed tool results). Recovery cannot apply here: these recordings kept only the first 300 characters of rejected outputs. Same model turns as live-2, so throttled questions stay failures.

| Metric | Result |
| --- | --- |
| Answer accuracy | 5/20 (25%) |
| Correct tool choice | 12/20 (60%) |
| Adversarial requests handled safely | 1/3 (33%) |
| Questions using fallback Cypher | 1 (calls: 2) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 0/5 (0%) |
| Questions hit by rate limiting (429) | 0 (failed because of it: 0) |
| Questions without an answer (errors) | 8 |
| Model tool calls rejected for schema mismatch | 16 |
| Recovered from malformed calls (valid answer sent to a non-existent tool) | 0 questions |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | Recovered | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | 103 |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 706, 259 |
| q03 | lookup | failure | **no** | yes | 2 | 0/0 | 0 | 0 |  | Novak Djokovic, 7-6(5) 1-6 7-6(4) 4-6 13-12(3) |
| q04 | h2h | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | 30, 28 |
| q05 | h2h | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | 14 |
| q06 | multi-hop | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 2 |
| q07 | multi-hop | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 0 | 0 |  | Novak Djokovic, 1 |
| q09 | prestige | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | Pete Sampras |
| q10 | prestige | failure | **no** | yes | 0 | 0/0 | 0 | 0 |  | 1 |
| q11 | styles | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | Jannik Sinner |
| q12 | styles | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 4 turns |  |
| q13 | prediction | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 2 turns |  |
| q14 | prediction | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q15 | ambiguous | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q16 | ambiguous | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q17 | out-of-scope | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q18 | adversarial | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q19 | adversarial | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | 0 | scope filter (no LLM call) |  |
