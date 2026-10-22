"""Verifier node: claims must be backed by the tool results they cite (decision log D64).

- verified: needs at least one successful cited tool call, and every number in the claim must appear
  in those results (rounding to the claim's precision allowed; '43%' matches 0.43 or 0.4289).
- predicted: must cite a successful predict_match call.
Anything else is downgraded to 'interpreted' with the reason. Cited match ids that appear in no cited
result are dropped; Cypher from cited fallback calls is attached to the claim.
"""

import json
import re

from app.agent.schema import AgentAnswer, Claim, ToolCallRecord

NUMBER = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*%)?")
MATCH_ID = re.compile(r"^[\w-]+$")


def numbers_in_text(text: str) -> list[tuple[float, int, bool]]:
    """(value, decimals, is_percent) for every number written in a claim."""
    found = []
    for raw, percent in NUMBER.findall(text):
        clean = raw.replace(",", "")
        decimals = len(clean.split(".")[1]) if "." in clean else 0
        found.append((float(clean), decimals, bool(percent)))
    return found


def numbers_in_value(value) -> list[float]:
    """Numeric fields of a tool result. Digits inside strings (dates, scores, ids) do not count:
    a head-to-head lists dozens of dates, so every day of the month would 'support' any small number."""
    if isinstance(value, bool):
        return []
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, str) and NUMBER.fullmatch(value.strip()):
        return [float(value.strip().replace(",", ""))]
    if isinstance(value, dict):
        return [n for item in value.values() for n in numbers_in_value(item)]
    if isinstance(value, list):
        return [n for item in value for n in numbers_in_value(item)]
    return []


def strings_in_value(value) -> set[str]:
    """String fields of a tool result that contain digits (dates, scores, match ids, eras)."""
    if isinstance(value, str):
        return {value} if any(ch.isdigit() for ch in value) and len(value) >= 3 else set()
    if isinstance(value, dict):
        return {s for item in value.values() for s in strings_in_value(item)}
    if isinstance(value, list):
        return {s for item in value for s in strings_in_value(item)}
    return set()


def unsupported_numbers(text: str, results: list) -> list[tuple[float, int, bool]]:
    """Numbers of the claim that no cited result supports.

    Dates, scores and ids are matched as whole strings and removed first; a remaining four-digit
    year is supported by a numeric field or by the year of a cited date.
    """
    strings = {s for result in results for s in strings_in_value(result)}
    for literal in sorted(strings, key=len, reverse=True):
        text = text.replace(literal, " ")
    pool = [n for result in results for n in numbers_in_value(result)]
    years = {float(s[:4]) for s in strings if s[:4].isdigit()}
    return [
        number for number in numbers_in_text(text)
        if not supported(number, pool) and not (number[1] == 0 and not number[2] and number[0] in years)
    ]


def supported(number: tuple[float, int, bool], pool: list[float]) -> bool:
    """A written number matches a result number when equal after rounding to the written precision."""
    value, decimals, percent = number
    targets = [(value / 100, decimals + 2), (value, decimals)] if percent else [(value, decimals)]
    return any(round(n, precision) == round(target, precision) for target, precision in targets for n in pool)


def downgrade(claim: Claim, reason: str) -> Claim:
    """Copy of the claim tagged interpreted, remembering why."""
    return claim.model_copy(update={"tag": "interpreted", "downgradedFrom": claim.tag, "downgradeReason": reason})


def check_claim(claim: Claim, trace: dict[str, ToolCallRecord]) -> Claim:
    """Apply the rules to one claim."""
    cited = [trace[s] for s in claim.sources if s in trace and trace[s].success]
    if claim.tag == "interpreted":
        return claim
    if not cited:
        return downgrade(claim, "no successful tool call cited")
    if claim.tag == "predicted":
        if not any(record.tool == "predict_match" for record in cited):
            return downgrade(claim, "predicted claims must cite predict_match")
        return claim
    missing = unsupported_numbers(claim.text, [record.result for record in cited])
    if missing:
        shown = ", ".join(f"{value:g}{'%' if percent else ''}" for value, _, percent in missing)
        return downgrade(claim, f"number(s) not found in cited results: {shown}")
    return claim


def attach_provenance(claim: Claim, trace: dict[str, ToolCallRecord]) -> Claim:
    """Keep only match ids present in cited results; attach the Cypher of cited fallback calls."""
    cited = [trace[s] for s in claim.sources if s in trace and trace[s].success]
    blob = json.dumps([record.result for record in cited], default=str)
    match_ids = [m for m in claim.matchIds if MATCH_ID.match(m) and f'"{m}"' in blob]
    cypher = next((r.result.get("cypher") for r in cited if r.tool == "run_readonly_cypher"), claim.cypher)
    return claim.model_copy(update={"matchIds": match_ids, "cypher": cypher})


def verify(answer: AgentAnswer, records: list[ToolCallRecord]) -> tuple[AgentAnswer, int]:
    """Verified answer and the number of downgraded claims."""
    trace = {record.id: record for record in records}
    claims = [attach_provenance(check_claim(claim, trace), trace) for claim in answer.claims]
    downgraded = sum(claim.downgradedFrom is not None for claim in claims)
    return answer.model_copy(update={"claims": claims}), downgraded
