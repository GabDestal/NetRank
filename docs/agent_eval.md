# Agent evaluation runs

Each run is kept; live runs are listed separately from replays (re-scoring recorded turns).

| Run | Mode | Model | Date | Accuracy | Tools | Adversarial safe | 429-affected | Note |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| [live-1](agent_eval/live-1.md) | live | `openai/gpt-oss-120b` | 2026-10-22 19:10 UTC | 8/20 (40%) | 17/20 (85%) | 3/3 (100%) | 18 |  |
| [live-2](agent_eval/live-2.md) | live | `openai/gpt-oss-120b` | 2026-10-22 19:30 UTC | 5/20 (25%) | 12/20 (60%) | 1/3 (33%) | 17 | Second live run, after fixes from live-1: field 'type', rejected turns recorded, names must come from the question, 20 s pause between questions. |
| [replay-of-live-1](agent_eval/replay-of-live-1.md) | replay | `replay of live-1` | 2026-10-22 19:29 UTC | 2/20 (10%) | 9/20 (45%) | 2/3 (67%) | 0 | Not a quality measure: live-1 did not record rejected turns and its answers use the old field name 'tag', so the fixed agent cannot replay it faithfully. See live-2. |
| [replay-of-live-2](agent_eval/replay-of-live-2.md) | replay | `replay of live-2` | 2026-10-22 19:53 UTC | 5/20 (25%) | 12/20 (60%) | 1/3 (33%) | 0 | Re-scores live-2's recorded turns with the fixed harness. Rejected turns replay as rejections and throttled questions have no turns, so this checks scoring consistency, not the fixes. |

## Aborted attempts and diagnostic calls (no scored results)

| Date | Model | Reason |
| --- | --- | --- |
| 2026-10-22 (recorded by hand afterwards) | `llama-3.3-70b-versatile` | q01: Groq 404 model_not_found (model retired). No question answered. |
| 2026-10-22 (recorded by hand afterwards) | `openai/gpt-oss-120b` | q01: Groq 400 tool_use_failed (submit_answer arguments did not match the schema) was not handled by the harness and crashed the run. Fixed before the next run: slimmer answer schema, one fed-back retry, per-question error rows. |
| 2026-10-22 (recorded by hand afterwards) | `openai/gpt-oss-120b` | Diagnostic single call on q01 after live-1, not an evaluation run: showed the model writes "type" where the schema said "tag". Led to the field rename in D65. |
| 2026-10-22 (recorded by hand afterwards) | `openai/gpt-oss-120b` | live-3, stopped after q13 when the machine ran low on memory (the run was killed before it saved its report). q01-q13 all ended as errors after 1-3 model turns; the error text was not kept (the console output was filtered and the report never written), so the cause is unknown. A minimal call right afterwards returned 200 with 926/1000 daily requests left, so the daily quota was not exhausted. Recordings kept in eval/recordings/live-3/. In q01 the model also called a non-existent 'json' tool for its answer (fed back as a rejection). |
