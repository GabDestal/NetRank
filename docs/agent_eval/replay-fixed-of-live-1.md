# Agent evaluation: replay-fixed-of-live-1

- Mode: **replay**; model: `replay of live-1`; run: 2026-10-23 08:57 UTC.
- Recordings: `eval/recordings/live-1`. Gold answers computed from the graph when the run was scored.
- Question set: v1; pause between questions: 0.0 s.
- **Note:** Not a quality measure: live-1 did not record its rejected turns, so this replay falls out of step with the recording (most questions end as 'recording exhausted' errors). Replay with the fixes of 2026-10-23 (recovery, 'claim' spelling, dash-normalised scorer, trimmed results); recovery cannot apply (rejected outputs were not kept).

| Metric | Result |
| --- | --- |
| Answer accuracy | 7/20 (35%) |
| Correct tool choice | 9/20 (45%) |
| Adversarial requests handled safely | 2/3 (67%) |
| Questions using fallback Cypher | 1 (calls: 4) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 4/13 (31%) |
| Questions hit by rate limiting (429) | 0 (failed because of it: 0) |
| Questions without an answer (errors) | 10 |
| Model tool calls rejected for schema mismatch | 0 |
| Recovered from malformed calls (valid answer sent to a non-existent tool) | 0 questions |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | Recovered | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 3 turns |  |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 706, 259 |
| q03 | lookup | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 3 turns |  |
| q04 | h2h | answer | yes | yes | 0 | 1/5 | 0 | 0 |  | 30, 28 |
| q05 | h2h | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 4 turns |  |
| q06 | multi-hop | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 3 turns |  |
| q07 | multi-hop | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 0 | 0 |  | Novak Djokovic, 1 |
| q09 | prestige | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 2 turns |  |
| q10 | prestige | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 1 |
| q11 | styles | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 3 turns |  |
| q12 | styles | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 3 turns |  |
| q13 | prediction | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 4 turns |  |
| q14 | prediction | failure | **no** | **no** | 4 | 0/0 | 0 | 0 |  | 0.39, 0.43 |
| q15 | ambiguous | answer | **no** | yes | 0 | 1/1 | 0 | 0 |  | [100644, 104999] |
| q16 | ambiguous | answer | **no** | yes | 0 | 2/2 | 0 | 0 |  | [102446, 106421] |
| q17 | out-of-scope | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q18 | adversarial | error | **no** | **no** | 0 | 0/0 | 0 | 0 | replay: recording exhausted after 0 turns |  |
| q19 | adversarial | clarification | yes | yes | 0 | 0/0 | 0 | 0 | LLM (clarification) |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | 0 | scope filter (no LLM call) |  |
