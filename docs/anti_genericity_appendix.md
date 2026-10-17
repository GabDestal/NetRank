# Anti-genericity appendix

I asked a chat model, with no project context, to design a Neo4j schema for this application. Its
answer is saved unedited in [`ai_baseline_schema.md`](ai_baseline_schema.md). This page compares it
with our schema: where they agree, where we chose differently and why (with the data behind it), and
what the baseline has that we left out. Decisions D1–D19 are in [`modeling_rationale.md`](modeling_rationale.md).

## Where the baseline matches us

A lot of it is the standard way to model ATT&CK, and we ended up in the same place:

| Baseline | Ours | Note |
|---|---|---|
| `:Technique:SubTechnique` + `SUBTECHNIQUE_OF` | D3 B | Same |
| `:Tactic` nodes, `IN_TACTIC` | D4 A | Same |
| `:Software:Malware` / `:Software:Tool` | D5 C | Same |
| Campaigns with `ATTRIBUTED_TO` | D6 B | Same |
| STIX id kept on every node, ATT&CK id unique | D1 C | We make both unique, the baseline only indexes the STIX id |
| `HAS_WEAKNESS` to `:CWE`, `Product`-`MADE_BY`-`Vendor` | D9 A, D10 B | Same |
| Technique overlap is the weakest evidence; T1190 flags almost every group | D12, Q3 | Same idea: Q3 is only "shares technique T", with a note in every response |
| Rank mitigations as a portfolio, greedily | D14 C | Same algorithm; we also report the techniques no mitigation covers (20, 5.9% of the weight) |
| Provenance on bridge edges | D7, D11 | `source`, `attack_version`, `mapping_date` on every bridge relationship |

On revoked objects we agree on the goal but not the method: the baseline loads them and filters
`revoked`/`deprecated` in every query, which is exactly the option we rejected in D2 (one forgotten
filter returns stale objects). We load only live v20 objects and remap the 6 stale CTID mappings
through `revoked-by` at import.

## Where we differ, and why

**1. `EXPLOITS` edges from a regex over ATT&CK text.** I ran `CVE-\d{4}-\d{4,7}` over the
description and external references of the 26,244 live objects in ATT&CK v20 (relationships included).

- 357 objects mention a CVE: 314 relationships, 18 techniques, 14 malware, 5 groups, 5 campaigns, 1 analytic.
  That is 180 distinct CVEs, 147 of them in KEV.
- No external reference has a CVE as `external_id`, so there is no structured field, as the baseline says.
  (8 references on techniques are named "NVD CVE-…" and link to NVD.)
- Assigning each hit to its group, software or campaign gives **285 actor–CVE pairs**. In 272 the CVE is
  in the object's own text, and 260 of those use "exploit", "vulnerability" or "leverage", e.g.
  *"Threat Group-3390 has exploited the Microsoft SharePoint vulnerability CVE-2019-0604"* or
  *"Sidewinder has exploited vulnerabilities … including CVE-2017-11882 and CVE-2020-0674"*.
  The other 12 still describe use (*"APT28 has used CVE-2015-4902 to bypass security features"*).
- 13 pairs come only from citation titles or URLs, and those are not evidence. For example, OilRig's
  links to `netstat` and `certutil` carry CVE-2017-11882 only because the cited FireEye report mentions it,
  and HAFNIUM is linked to CVE-2021-44228 the same way.
- Coverage: the 272 text pairs reach **138 of 1,745 KEV CVEs (7.9%)** and 66 of 178 groups.
  **81 of those 138 CVEs have no CTID mapping**, so our graph cannot link them to any group today.

So the baseline is right that the text holds real exploitation evidence. Section 0 of the rationale
said "no live ATT&CK object references a CVE"; that was only true of structured fields and is now corrected.
We still did not add `EXPLOITS`: it covers 8% of KEV against CTID's 24%, each pair needs checking
(13 of 285 rest only on a citation title), and D12 keeps every link that is not a verified structured fact
out of the verified relationship types. This would be a reasonable extension: a separate
`MENTIONED_EXPLOITING {quote, citation}` type, limited to own-text pairs, shown as its own evidence tier.

**2. `ENABLES {mappingType}` instead of three types.** This is our rejected D11 A. We use `EXPLOITS_VIA`,
`PRIMARY_IMPACT`, `SECONDARY_IMPACT`, so Q2 and Q3 filter by relationship type, not by a property.

**3. One `:CPE` node per version.** Rejected in D10 C. NVD gives ranges, not version lists: `cisco:ios` alone
has 1,973 `cpeMatch` entries for 39 CVEs. Enumerating versions needs the CPE dictionary or an asset
inventory, which we don't have, so ranges stay as properties on `AFFECTS`.

**4. CVSS from NVD only.** 311 KEV CVEs (18%) have no NVD primary score. The baseline's
`sum(weight * c.cvssBaseScore)` would silently skip them; D8 A1 falls back to the CNA score and records the source.

**5. Inferred links on the same edge types with a `confidence` property.** This is D12 A, rejected: one
missing filter mixes inferred and verified links. Ours go to `INFERRED_MAPS_TO` (D18).

We also added what the baseline doesn't have: procedure text on `USES` for citations (D7), SSVC fields (D8),
`:ImportMeta` provenance per source, stored GDS results (D15, D16), live similarity (D17), and the agent guardrails (D19).

## What the baseline has that we don't

| Baseline item | Verdict |
|---|---|
| EPSS score on `:CVE` | Reasonable extension: one CSV keyed by CVE id. Less useful here because every CVE in our graph is already known exploited (KEV) |
| `:KEVEntry` as a separate node | Out of scope: our graph only holds KEV CVEs, so it would be a 1:1 hop; `date_added`, `due_date`, `required_action`, ransomware use are on `:CVE`. A separate node only pays off with KEV history across snapshots |
| `:CPE` per version | Out of scope without an inventory (point 3) |
| CAPEC (`CWE` ↔ `CAPEC` ↔ `Technique`) | Reasonable extension: a second, weaker CVE → technique route for the 76% unmapped CVEs. Not measured; it would also need its own inferred relationship type |
| `Organization`, `Asset`, `Sector`, `EXPOSED_TO` | Out of scope: there is no CMDB or scanner data in a course project. Q7 takes the product key as input instead, which is the same question for one product |
| `IMPLEMENTS` (org → mitigation) | Reasonable extension, but as a request parameter, not a node: the D14 plan could skip mitigations the user already has. Needs no new data |

None of these were added to the schema.
