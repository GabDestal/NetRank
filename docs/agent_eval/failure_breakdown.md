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

## Fixes of 2026-10-23 and re-scoring by replay

| Cause | Fix (decision log) | Re-scorable on live-1 to live-3? |
| --- | --- | --- |
| Model quirk: answer sent to `json` / `commentary` | Recovery when the payload is a valid, verified `submit_answer` (D71) | No: those recordings kept only 300 characters of the rejected output |
| Model quirk: `claim` field spelling | Accepted like `statement` (D65, D71) | Yes (live-3 q07) |
| API error: 429 | 429 message and headers logged; daily cap stops the run, rest "not run"; ~30% fewer prompt tokens (D72, D73) | No: same recorded turns |
| Scorer: Unicode hyphens | Normalised on both sides (D74) | Yes (live-3 q03) |

Replays of the recorded model turns with these fixes (new runs; the originals are unchanged):

| Run | Original | Replay with fixes | Change |
| --- | ---: | ---: | --- |
| live-1 | 8/20 | 7/20 | not a quality measure: live-1 did not record its rejected turns, so the replay falls out of step |
| live-2 | 5/20 | 5/20 | none: 7 answers went to `json` / `commentary`, but their outputs were cut at 300 characters, so whether they would pass recovery cannot be checked |
| live-3 | 10/20 | 12/20 | q03 (scorer), q07 (`claim` spelling) |

## Prompt tokens per question

Estimated with `scripts/measure_tokens.py` on live-3's recordings (same model turns, o200k_base encoding):

| | Per question | Per turn | Tool specs per turn |
| --- | ---: | ---: | ---: |
| Before (live-3 code) | 10,984 | 2,981 | 2,215 |
| After (D72) | 7,647 | 2,076 | 1,531 |

## live-5 (2026-10-24, fresh daily window)

The first full v2 run on a fresh daily quota (started 09:20 UTC, about 24 h after the last Groq call, checked by
the quota log, D77). 22/24 correct, 19/20 on the v1 questions. Per-minute 429s hit q14 (1) and q21 (3); each was
retried and none caused a failure. The daily cap was not reached: 94,211 prompt and 12,037 completion tokens
(Groq counts; the 3 questions answered without a counted call show 0: q17 and q18 were recovered from rejected
calls, q20 was refused by the scope filter before any call).

| Question | Cause | Detail |
| --- | --- | --- |
| q14 (model + Pinnacle for 2019 Wimbledon SF) | step limit | `predict_match` succeeded at step 3; after an EXPLAIN rejection on invented `p1_odds`/`p2_odds` (step 4), a Cypher query returning the Pinnacle prices succeeded at step 5. The model then kept querying (two queries with 0 rows, one more lookup) until the 8-step limit, without submitting an answer |
| q21 (Federer's longest Wimbledon match) | retry cap blocked a correct query; step limit | First live EXPLAIN rejection followed by a corrected retry: `m.duration`/`m.opponent` rejected, the retry with `m.minutes` accepted. That query sorted `ORDER BY minutes DESC` without excluding nulls, so Neo4j returned a match with no duration first. The model then used `exists(m.minutes)` (removed in Neo4j 5), rejected by EXPLAIN; its next query, with `m.minutes IS NOT NULL`, was correct (it returns 297 min, 2019 final vs Djokovic) but was refused by the rule that blocks Cypher after two rejections. The run ended at the step limit |

Neither failure is a wrong answer: both end as an explicit failure ("stopped after the maximum number of steps").
The verifier downgraded one claim in q03 and one in q09 (2 of 16 checkable claims). No fix was applied after this
run; any change will be re-scored as `replay-fixed-of-live-5` next to it, not in place of it.
