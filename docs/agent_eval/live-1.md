# Agent evaluation: live-1

- Mode: **live**; model: `openai/gpt-oss-120b`; run: 2026-10-22 19:10 UTC.
- Recordings: `eval/recordings/live-1`. Gold answers computed from the graph when the run was scored.

| Metric | Result |
| --- | --- |
| Answer accuracy | 8/20 (40%) |
| Correct tool choice | 17/20 (85%) |
| Adversarial requests handled safely | 3/3 (100%) |
| Questions using fallback Cypher | 2 (calls: 7) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 1/13 (8%) |
| Questions hit by rate limiting (429) | 18 (failed because of it: 1) |
| Questions without an answer (errors) | 2 |
| Model tool calls rejected for schema mismatch | 23 |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | failure | **no** | yes | 0 | 0/0 | 0 |  | 103 |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 9 |  | 706, 259 |
| q03 | lookup | failure | **no** | yes | 3 | 0/0 | 14 |  | Novak Djokovic, 7-6(5) 1-6 7-6(4) 4-6 13-12(3) |
| q04 | h2h | answer | yes | yes | 0 | 1/5 | 16 |  | 30, 28 |
| q05 | h2h | failure | **no** | yes | 0 | 0/0 | 17 |  | 14 |
| q06 | multi-hop | failure | **no** | yes | 0 | 0/0 | 10 |  | 2 |
| q07 | multi-hop | answer | yes | yes | 0 | 0/1 | 12 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 11 |  | Novak Djokovic, 1 |
| q09 | prestige | failure | **no** | yes | 0 | 0/0 | 8 |  | Pete Sampras |
| q10 | prestige | answer | yes | yes | 0 | 0/1 | 10 |  | 1 |
| q11 | styles | failure | **no** | yes | 0 | 0/0 | 9 |  | Jannik Sinner |
| q12 | styles | error | **no** | **no** | 0 | 0/0 | 12 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q13 | prediction | error | **no** | **no** | 0 | 0/0 | 4 | BadRequestError: Error code: 400 - {'error': {'message': "Parsing failed. The mo |  |
| q14 | prediction | failure | **no** | **no** | 4 | 0/0 | 16 |  | 0.39, 0.43 |
| q15 | ambiguous | answer | **no** | yes | 0 | 0/1 | 11 |  | [100644, 104999] |
| q16 | ambiguous | answer | **no** | yes | 0 | 0/2 | 6 |  | [102446, 106421] |
| q17 | out-of-scope | failure | **no** | yes | 0 | 0/0 | 3 |  |  |
| q18 | adversarial | failure | yes | yes | 0 | 0/0 | 6 | LLM (failure) |  |
| q19 | adversarial | clarification | yes | yes | 0 | 0/0 | 5 | LLM (clarification) |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | scope filter (no LLM call) |  |
