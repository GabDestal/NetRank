# Link prediction: evaluation (D18)

**Goal:** suggest ATT&CK techniques for the 1,326 KEV CVEs (76%) that CTID doesn't map, so that
questions 3, 5 and 7 don't miss them. Suggestions would be stored as `INFERRED_MAPS_TO`, apart
from the verified CTID links.

**Result:** the model does not beat a simple baseline, so **nothing is stored**. `make predict`
records this in `:ImportMeta {source: 'predict'}`, and the CVE endpoint shows an empty, labelled
suggestion list with the reason.

Run on 2026-10-15 with `make predict`. Full numbers: `data/processed/link_prediction_report.json`.

## How it was evaluated

**Split by CVE and by date.** The real targets are CVEs with no known technique at all, so the
test has to look the same: all techniques of a validation or test CVE are hidden. The 419 mapped
CVEs are sorted by the date KEV added them:

| Split | CVEs | KEV date added |
|---|---|---|
| Train | 248 | 2021-11-03 to 2023-11-07 |
| Validation | 84 | 2023-11-13 to 2025-03-03 |
| Test | 87 | 2025-03-04 to 2025-07-28 |

The cut is on whole dates, so CVEs added on the same day stay together.

**No leakage in the features.** Every graph feature only uses the techniques of training CVEs, and
a CVE never counts itself (leave-one-out). A technique only seen in validation or test can't be
suggested, but it still counts as a miss in recall.

**Candidates:** for each CVE, the 125 techniques that appear in training.

**Features** (12 per CVE–technique pair):

- `technique_prior`: share of training CVEs mapped to the technique
- `cwe_vote`, `product_vote`, `vendor_vote`: among training CVEs sharing a CWE / product / vendor
  with this CVE, the share mapped to the technique
- `cwe_neighbours`, `product_neighbours`, `vendor_neighbours`: how many such CVEs there are
- `cvss_score`, `ssvc_exploitation_active`, `ssvc_automatable`, `ssvc_impact_total`,
  `known_ransomware_use`: the CVE's own properties

**Models:** random forest (300 trees, `min_samples_leaf=5`, balanced class weights) and logistic
regression, both from scikit-learn.

**Baseline:** "suggest the most common techniques", i.e. score every pair by `technique_prior`.
Every CVE gets the same top 3.

**Metrics:** precision@3 and recall@3 (averaged over CVEs), plus AUCPR over all pairs.

## Results

| Test (87 newest CVEs) | AUCPR | Precision@3 | Recall@3 |
|---|---|---|---|
| Random forest | 0.179 | 0.253 | 0.275 |
| Logistic regression | 0.171 | 0.295 | 0.325 |
| **Most common techniques** | 0.175 | **0.276** | 0.312 |

| Validation (84 CVEs) | AUCPR | Precision@3 | Recall@3 |
|---|---|---|---|
| Random forest | 0.214 | 0.286 | 0.360 |
| Logistic regression | 0.247 | 0.333 | 0.423 |
| Most common techniques | 0.238 | 0.317 | 0.397 |

The gate needs at least +0.05 precision@3 over the baseline and a higher AUCPR on test. The random
forest is *below* the baseline on precision@3, so it fails.

**Threshold:** the plan was to pick it on validation so that kept suggestions reach about 70%
precision. No threshold gets there: even the best-ranked suggestions are right far less often.

**Feature importance** (random forest, test set):

| Feature | Permutation importance (AUCPR drop) | Impurity importance |
|---|---|---|
| technique_prior | 0.114 | 0.396 |
| cwe_vote | 0.032 | 0.126 |
| vendor_vote | 0.030 | 0.173 |
| vendor_neighbours | 0.014 | 0.053 |
| product_vote | 0.013 | 0.068 |
| product_neighbours | 0.009 | 0.048 |
| cvss_score | 0.005 | 0.039 |
| cwe_neighbours | 0.004 | 0.064 |
| ssvc_impact_total | 0.002 | 0.006 |
| known_ransomware_use | 0.001 | 0.016 |
| ssvc_exploitation_active | 0.000 | 0.000 |
| ssvc_automatable | −0.002 | 0.011 |

Popularity does most of the work. Shared CWEs and vendors add a bit; the CVE's own properties add
almost nothing (SSVC exploitation is "active" for nearly every KEV CVE, so it can't help).

## Why the first trial looked so much better

The first trial (in `modeling_rationale.md`, D18) reported AUCPR 0.75. It used the GDS pipeline,
which hides random *edges*: a test CVE kept its other techniques, so the model could recognise
it. It also used one non-link per link, while in reality almost every CVE–technique pair is a
non-link. With CVEs fully hidden and all candidates scored, AUCPR drops to 0.18.

## What else I tried (validation only)

To check it wasn't just a bad setting, I tried a few variants. I only looked at validation, so the
test numbers above stay clean.

| Variant | Validation AUCPR | Validation precision@3 | Baseline precision@3 |
|---|---|---|---|
| Random forest, `min_samples_leaf=1` | 0.151 | 0.238 | 0.317 |
| Random forest, `min_samples_leaf=20` | 0.218 | 0.302 | 0.317 |
| Random forest, no class weights, `min_samples_leaf=10` | 0.278 | 0.329 | 0.317 |
| Random forest + "lift" features (vote ÷ prior) | 0.231 | 0.294 | 0.317 |
| Exploitation technique only (`EXPLOITS_VIA`) | 0.092 | 0.121 | 0.133 |
| KEV name + description words (TF-IDF), logistic regression | 0.317 | 0.345 | 0.317 |
| Random forest + text score (out-of-fold) | 0.292 | 0.349 | 0.317 |

The best variant gains about +0.03 precision@3, still below the +0.05 gate and nowhere near 70%
precision. Text helps more than the graph features, which makes sense: CTID maps a CVE mainly
from the kind of bug it is ("command injection", "privilege escalation"), and that is in the KEV
text more than in shared CWEs or products. I didn't keep the text features, because they still
don't pass the gate and they move the model away from the graph.

## Hand-check of 20 suggestions

The random forest's top suggestion for 20 test CVEs picked at random (seed 42). "Plausible" means
the technique makes sense for the bug, whether or not CTID lists it.

| CVE | Vulnerability | Top suggestion | Prob. | In CTID? | Label | Why |
|---|---|---|---|---|---|---|
| CVE-2021-32030 | ASUS routers improper authentication | T1190 Exploit Public-Facing Application | 0.54 | no | plausible | Remote auth bypass on an internet-facing admin page |
| CVE-2023-0386 | Linux kernel improper ownership management | T1059 Command and Scripting Interpreter | 0.55 | no | implausible | Local privilege escalation; T1068 would fit |
| CVE-2024-11120 | GeoVision OS command injection | T1059 | 0.92 | no | plausible | Command injection runs shell commands |
| CVE-2024-12987 | DrayTek Vigor OS command injection | T1059 | 0.90 | yes | plausible | Same as above |
| CVE-2024-13159 | Ivanti EPM absolute path traversal | T1059 | 0.71 | no | implausible | Used to coerce credentials, not to run commands |
| CVE-2024-20439 | Cisco Smart Licensing static credential | T1059 | 0.60 | no | implausible | A hard-coded account; T1078 Valid Accounts would fit |
| CVE-2024-54085 | AMI MegaRAC authentication bypass | T1059 | 0.86 | no | implausible | Remote takeover of the BMC; nothing about scripting |
| CVE-2024-57968 | VeraCore unrestricted file upload | T1505.003 Web Shell | 0.57 | no | plausible | File upload bugs are a classic way to drop a web shell |
| CVE-2024-58136 | Yii improper protection of alternate path | T1059 | 0.75 | yes | plausible | Exploited for code execution |
| CVE-2024-6047 | GeoVision OS command injection | T1059 | 0.92 | yes | plausible | Command injection |
| CVE-2025-1976 | Brocade Fabric OS code injection | T1059 | 0.79 | yes | plausible | Code injection |
| CVE-2025-21590 | Juniper Junos improper isolation | T1059 | 0.47 | yes | plausible | Lets a local attacker inject code |
| CVE-2025-31161 | CrushFTP authentication bypass | T1059 | 0.87 | yes | plausible | Matches CTID, though the bypass itself is more T1078/T1190 |
| CVE-2025-33053 | Windows external control of file name or path | T1068 Exploitation for Privilege Escalation | 0.81 | no | implausible | Remote code execution through a file the user opens, not privilege escalation |
| CVE-2025-42599 | Active! Mail stack-based buffer overflow | T1203 Exploitation for Client Execution | 0.65 | no | implausible | A server-side webmail bug; T1190 would fit |
| CVE-2025-43200 | Apple multiple products, unspecified | T1204.001 Malicious Link | 0.32 | no | implausible | The reported attacks needed no click from the victim |
| CVE-2025-47812 | Wing FTP null byte handling | T1059 | 0.90 | yes | plausible | Exploited for code execution |
| CVE-2025-48928 | TeleMessage core dump exposure | T1059 | 0.41 | no | implausible | An information leak, nothing is executed |
| CVE-2025-5419 | Chromium V8 out-of-bounds read/write | T1203 Exploitation for Client Execution | 0.66 | yes | plausible | Browser memory bug exploited through a web page |
| CVE-2025-6558 | Chromium ANGLE improper input validation | T1059 | 0.71 | no | implausible | A browser sandbox escape; T1203 would fit |

**11 plausible, 9 implausible. 8 match CTID.** Three plausible ones aren't in CTID (ASUS → T1190,
GeoVision → T1059, VeraCore → web shell), so the model isn't always wrong when it disagrees with
CTID. But T1059 is the top suggestion for **14 of the 20**, whatever the bug is. That is the same
popularity bias the metrics show, and it's why the implausible cases look the way they do.

## Conclusion

On an honest split, graph features around a CVE (shared CWE, product, vendor) don't predict its
techniques better than "suggest the most common ones". `make predict` keeps the full workflow
(split, features, two models, baseline, gate, threshold rule, importances, hand-check) and will
store suggestions automatically if a future data release or better features pass the gate. Until
then, `INFERRED_MAPS_TO` stays empty.
