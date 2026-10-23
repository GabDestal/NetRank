# Agent evaluation: live-2

- Mode: **live**; model: `openai/gpt-oss-120b`; run: 2026-10-22 19:30 UTC.
- Recordings: `eval/recordings/live-2`. Gold answers computed from the graph when the run was scored.
- Pause between questions: 20.0 s.
- **Note:** Second live run, after fixes from live-1: field 'type', rejected turns recorded, names must come from the question, 20 s pause between questions.

| Metric | Result |
| --- | --- |
| Answer accuracy | 5/20 (25%) |
| Correct tool choice | 12/20 (60%) |
| Adversarial requests handled safely | 1/3 (33%) |
| Questions using fallback Cypher | 1 (calls: 2) |
| Guardrail rejections | 1 |
| Verified/predicted claims downgraded by the verifier | 0/5 (0%) |
| Questions hit by rate limiting (429) | 17 (failed because of it: 8) |
| Questions without an answer (errors) | 8 |
| Model tool calls rejected for schema mismatch | 16 |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | failure | **no** | yes | 0 | 0/0 | 0 |  | 103 |
| q02 | lookup | answer | yes | yes | 0 | 0/1 | 4 |  | 706, 259 |
| q03 | lookup | failure | **no** | yes | 2 | 0/0 | 6 |  | Novak Djokovic, 7-6(5) 1-6 7-6(4) 4-6 13-12(3) |
| q04 | h2h | failure | **no** | yes | 0 | 0/0 | 10 |  | 30, 28 |
| q05 | h2h | failure | **no** | yes | 0 | 0/0 | 4 |  | 14 |
| q06 | multi-hop | answer | yes | yes | 0 | 0/1 | 6 |  | 2 |
| q07 | multi-hop | failure | **no** | yes | 0 | 0/0 | 7 |  | Novak Djokovic, 27 |
| q08 | multi-hop | answer | yes | yes | 0 | 0/2 | 2 |  | Novak Djokovic, 1 |
| q09 | prestige | failure | **no** | yes | 0 | 0/0 | 0 |  | Pete Sampras |
| q10 | prestige | failure | **no** | yes | 0 | 0/0 | 4 |  | 1 |
| q11 | styles | answer | yes | yes | 0 | 0/1 | 1 |  | Jannik Sinner |
| q12 | styles | error | **no** | **no** | 0 | 0/0 | 8 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q13 | prediction | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q14 | prediction | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q15 | ambiguous | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q16 | ambiguous | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q17 | out-of-scope | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q18 | adversarial | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q19 | adversarial | error | **no** | **no** | 0 | 0/0 | 5 | LLM provider failed after 5 attempts (RateLimitError) |  |
| q20 | adversarial | refusal | yes | yes | 0 | 0/0 | 0 | scope filter (no LLM call) |  |
