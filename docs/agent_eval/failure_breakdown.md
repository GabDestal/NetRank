# Failure breakdown, live runs 1-3

Every question scored wrong in a live run, by cause. Model: `openai/gpt-oss-120b` on the Groq free tier,
runs on 2026-10-22 (live-1, live-2) and 2026-10-23 (live-3). The runs themselves:
[live-1](live-1.md), [live-2](live-2.md), [live-3](live-3.md).

| Cause | live-1 | live-2 | live-3 | Total |
| --- | --- | --- | --- | --- |
| Model quirk: invalid tool call (made-up tool, wrong field name, unparseable output) | 8 | 7 | 2 | 17 |
| API error: rate limit (429) still failing after every retry | 1 | 8 | 7 | 16 |
| Player resolution: ambiguous name answered instead of asked | 2 | 0 | 0 | 2 |
| Tool choice: wrong tools for the question | 1 | 0 | 0 | 1 |
| Scorer: correct answer not matched by the scorer | 0 | 0 | 1 | 1 |
| Guardrail rejection (as the cause of a wrong answer) | 0 | 0 | 0 | 0 |
| Verifier downgrade (as the cause of a wrong answer) | 0 | 0 | 0 | 0 |
| **Wrong answers** | **12** | **15** | **10** | **37** |
| Correct answers | 8 | 5 | 10 | 23 |

## Per question

| Run | Id | Cause | Detail |
| --- | --- | --- | --- |
| live-1 | q01, q03, q05, q06, q09, q11, q17 | Model quirk | Two `submit_answer` calls rejected by Groq (400 tool_use_failed), ending as a failure. The rejection text was not recorded in live-1; the diagnostic call that followed showed the model writing `type` where the schema said `tag` |
| live-1 | q13 | Model quirk | Groq 400 "Parsing failed": the model's output could not be parsed as a tool call |
| live-1 | q12 | API error | 429 on every attempt (5) |
| live-1 | q14 | Tool choice | Fallback Cypher instead of `predict_match` with the match context; one Cypher rejected by the guardrail, which worked as intended |
| live-1 | q15, q16 | Player resolution | "Zverev" / "Medvedev" expanded by the model to one player instead of a clarification (fixed after live-1: search must use the user's words) |
| live-2 | q01, q03, q04, q05, q07, q09, q10 | Model quirk | Answer sent to tools that don't exist (`json` 6x, `commentary` 1x) and/or `submit_answer` claims missing `text` (the model wrote `statement`); two rejections, then failure |
| live-2 | q12-q19 | API error | 429 on every attempt (5) |
| live-3 | q05 | Model quirk | Calls to made-up tools: `head_to_handa`, then `commentary` |
| live-3 | q07 | Model quirk | Answer sent to `json`, then `submit_answer` with a third field spelling (`claim`), rejected by our schema |
| live-3 | q13-q19 | API error | 429 on every attempt (6, each waiting up to 60 s for the token window); the 429 message was not logged, so per-minute vs per-day limit is unknown |
| live-3 | q03 | Scorer | Right winner and score, but the model wrote the score with non-breaking hyphens (U+2011), which the scorer compared as different characters |

## Notes

- Rejections that the retry rescued are not failures and are not counted above. The `json` / `commentary`
  calls always carried a well-formed answer: the model put a valid answer in the wrong tool.
- q18 (write attempt) was never caught by a Cypher guardrail in any run: the model refused or stopped
  itself without generating Cypher (live-1, smoke test), or the question was throttled (live-2, live-3).
  The graph was unchanged after every run.
