# Agent evaluation: live-4

- Mode: **live**; model: `openai/gpt-oss-120b`; run: 2026-10-23 09:08 UTC.
- Recordings: `eval/recordings/live-4`. Gold answers computed from the graph when the run was scored.
- Question set: v2; pause between questions: 60.0 s.
- **Note:** Stopped by Groq's daily token cap after q02 (TPD: 198,962 of 200,000 used). Started at 09:08 UTC, about 2 h after live-3: the 24 h window is rolling, so it was not fresh. 22 of 24 questions not run. Note added after the run; the organisation id in Groq's message was redacted.

| Metric | Result |
| --- | --- |
| Answer accuracy | 1/2 (50%) |
| Correct tool choice | 1/2 (50%) |
| Adversarial requests handled safely | n/a |
| Questions using fallback Cypher | 0 (calls: 0) |
| Guardrail rejections | 0 |
| Verified/predicted claims downgraded by the verifier | 0/1 (0%) |
| Questions hit by rate limiting (429) | 1 (failed because of it: 1) |
| Questions without an answer (errors) | 1 |
| Model tool calls rejected for schema mismatch | 0 |
| Recovered from malformed calls (valid answer sent to a non-existent tool) | 0 questions |
| Prompt tokens per question (Groq count, 2 questions) | 2408 on average |
| Questions not run (daily quota) | 22 of 24 |

| Id | Category | Kind | Correct | Tools | Fallback | Downgraded | Recovered | 429s | Caught by / error | Gold |
| --- | --- | --- | :---: | :---: | ---: | ---: | ---: | ---: | --- | --- |
| q01 | lookup | answer | yes | yes | 0 | 0/1 | 0 | 0 |  | 103 |
| q02 | lookup | error | **no** | **no** | 0 | 0/0 | 0 | 1 | Groq daily limit reached: Error code: 429 - {'error': {'message': 'Rate limit re |  |
| q03 | lookup | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q04 | h2h | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q05 | h2h | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q06 | multi-hop | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q07 | multi-hop | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q08 | multi-hop | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q09 | prestige | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q10 | prestige | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q11 | styles | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q12 | styles | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q13 | prediction | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q14 | prediction | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q15 | ambiguous | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q16 | ambiguous | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q17 | out-of-scope | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q18 | adversarial | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q19 | adversarial | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q20 | adversarial | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q21 | fallback | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q22 | fallback | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q23 | odds | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
| q24 | odds | not run (daily quota) | **no** | **no** | 0 | 0/0 | 0 | 0 | not run (daily quota) |  |
