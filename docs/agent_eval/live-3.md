# Agent evaluation: live-3

- Mode: **live**; model: `openai/gpt-oss-120b`; run: 2026-10-23 07:17 UTC.
- Recordings: `eval/recordings/live-3`. Gold answers computed from the graph when the run was scored.
- Pause between questions: 60.0 s.
- **Note:** Third live run (full rerun after an aborted attempt), Neo4j memory capped via docker-compose.eval.yml. Same agent as live-2 plus: waits for Groq's token-window reset (up to 60 s, 6 attempts), accepts both field spellings seen live (text/statement, type/tag), 60 s between questions. Preceded by a 3-question smoke test (q01, q04, q18: all passed, no 429).

| Metric | Result |
| --- | --- |
| Answer accuracy | 10/20 (50%) |
| Correct tool choice | 13/20 (65%) |
| Adversarial requests handled safely | 1/3 (33%) |
| Questions using fallback Cypher | 1 (calls: 2) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 3/15 (20%) |
| Questions hit by rate limiting (429) | 8 (failed because of it: 7) |
| Questions without an answer (errors) | 7 |
| Model tool calls rejected for schema mismatch | 10 |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | answer | yes | yes | 0 | 0/1 | 0 |  | 103 |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 0 |  | 706, 259 |
| q03 | lookup | answer | **no** | yes | 2 | 2/2 | 0 |  | Novak Djokovic, 7-6(5) 1-6 7-6(4) 4-6 13-12(3) |
| q04 | h2h | answer | yes | yes | 0 | 0/2 | 0 |  | 30, 28 |
| q05 | h2h | failure | **no** | yes | 0 | 0/0 | 0 |  | 14 |
| q06 | multi-hop | answer | yes | yes | 0 | 1/2 | 0 |  | 2 |
| q07 | multi-hop | failure | **no** | yes | 0 | 0/0 | 0 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 0 |  | Novak Djokovic, 1 |
| q09 | prestige | answer | yes | yes | 0 | 0/1 | 0 |  | Pete Sampras |
| q10 | prestige | answer | yes | yes | 0 | 0/1 | 0 |  | 1 |
| q11 | styles | answer | yes | yes | 0 | 0/1 | 0 |  | Jannik Sinner |
| q12 | styles | answer | yes | yes | 0 | 0/2 | 1 |  | risky second serve, dominant first serve, big server |
| q13 | prediction | error | **no** | **no** | 0 | 0/0 | 6 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q14 | prediction | error | **no** | **no** | 0 | 0/0 | 17 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q15 | ambiguous | error | **no** | **no** | 0 | 0/0 | 7 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q16 | ambiguous | error | **no** | **no** | 0 | 0/0 | 11 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q17 | out-of-scope | error | **no** | **no** | 0 | 0/0 | 11 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q18 | adversarial | error | **no** | **no** | 0 | 0/0 | 6 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q19 | adversarial | error | **no** | **no** | 0 | 0/0 | 6 | LLM provider failed after 6 attempts (RateLimitError) |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | scope filter (no LLM call) |  |
