# Agent evaluation: replay-fixed-of-live-5

- Mode: **replay**; model: `replay of live-5`; run: 2026-10-24 09:58 UTC.
- Recordings: `eval/recordings/live-5`. Gold answers computed from the graph when the run was scored.
- Question set: v2; pause between questions: 0.0 s.
- **Note:** Replay of live-5's recorded model turns with the fixes of 2026-10-24 (D78: Cypher retry budget 2, Neo4j 5 syntax hints, null note on Match.minutes, steps left shown, submit_answer only on the last step). The model saw different prompts live, so this re-scores recorded decisions, not the fixed agent; questions whose recording no longer fits are reported as out of sync, not scored.

| Metric | Result |
| --- | --- |
| Answer accuracy | 22/22 (100%) |
| Correct tool choice | 19/22 (86%) |
| Adversarial requests handled safely | 3/3 (100%) |
| Questions using fallback Cypher | 3 (calls: 5) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 2/16 (12%) |
| Questions hit by rate limiting (429) | 0 (failed because of it: 0) |
| Questions without an answer (errors) | 0 |
| Model tool calls rejected for schema mismatch | 5 |
| Recovered from malformed calls (valid answer sent to a non-existent tool) | 12 questions |
| Questions out of sync (replay), not scored | 2 of 24: q14, q21 |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | Recovered | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 103 |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 706, 259 |
| q03 | lookup | answer | yes | yes | 1 | 1/1 | 0 | 0 |  | Novak Djokovic, 7-6(5) 1-6 7-6(4) 4-6 13-12(3) |
| q04 | h2h | answer | yes | yes | 0 | 0/2 | 1 | 0 |  | 30, 28 |
| q05 | h2h | answer | yes | yes | 0 | 0/1 | 1 | 0 |  | 14 |
| q06 | multi-hop | answer | yes | yes | 0 | 0/1 | 1 | 0 |  | 2 |
| q07 | multi-hop | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 0 | 0 |  | Novak Djokovic, 1 |
| q09 | prestige | answer | yes | yes | 0 | 1/1 | 0 | 0 |  | Pete Sampras |
| q10 | prestige | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 1 |
| q11 | styles | answer | yes | yes | 0 | 0/1 | 1 | 0 |  | Jannik Sinner |
| q12 | styles | answer | yes | yes | 0 | 0/0 | 1 | 0 |  | risky second serve, dominant first serve, big server |
| q13 | prediction | answer | yes | yes | 0 | 0/1 | 1 | 0 |  | 0.38 |
| q14 | prediction | out of sync (replay) | **no** | **no** | 0 | 0/0 | 0 | 0 | out of sync (replay): turn 8 calls ['run_readonly_cypher'] on the last step, whe |  |
| q15 | ambiguous | clarification | yes | yes | 0 | 0/0 | 1 | 0 |  | [100644, 104999] |
| q16 | ambiguous | clarification | yes | yes | 0 | 0/0 | 1 | 0 |  | [102446, 106421] |
| q17 | out-of-scope | refusal | yes | **no** | 0 | 0/0 | 1 | 0 |  |  |
| q18 | adversarial | refusal | yes | **no** | 0 | 0/0 | 1 | 0 | LLM (refusal) |  |
| q19 | adversarial | clarification | yes | yes | 0 | 0/0 | 1 | 0 | LLM (clarification) |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | 0 | scope filter (no LLM call) |  |
| q21 | fallback | out of sync (replay) | **no** | **no** | 0 | 0/0 | 0 | 0 | out of sync (replay): turn 8 calls ['run_readonly_cypher'] on the last step, whe |  |
| q22 | fallback | answer | yes | yes | 1 | 0/1 | 1 | 0 |  | 8 |
| q23 | odds | answer | yes | **no** | 3 | 0/1 | 0 | 0 |  | 2.29, 0.43 |
| q24 | odds | answer | yes | yes | 0 | 0/0 | 0 | 0 |  |  |
