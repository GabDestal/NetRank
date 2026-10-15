"""make predict: suggest ATT&CK techniques for KEV CVEs that CTID does not map (D18).

1. Load every KEV CVE with its CWEs, products, vendors, CVSS/SSVC and verified techniques.
2. Evaluate on a CVE-disjoint temporal split (train on older CVEs, validate, test on the newest):
   random forest vs logistic regression vs the "most common techniques" baseline.
3. Choose the threshold on validation so that kept suggestions reach about 70% precision.
4. Gate: only if the random forest clearly beats the baseline and a threshold exists, refit on every
   mapped CVE and store at most 3 suggestions per unmapped CVE as INFERRED_MAPS_TO.
5. Either way, previous suggestions are removed and the run is recorded in :ImportMeta {source: 'predict'}
   with its status and metrics, so the graph always reflects the latest evaluation.

Usage:
    python -m scripts.predict                  # evaluate, gate, store if the gate passes
    python -m scripts.predict --evaluate-only  # evaluate and report, change nothing in Neo4j
    python -m scripts.predict --force          # store even if the gate fails
"""

import argparse
import hashlib
import json
import logging
import random
from datetime import date
from pathlib import Path
from typing import Any

from neo4j import Driver, RoutingControl
from sklearn.inspection import permutation_importance

from app.database.batch import run_batched
from scripts import link_prediction as lp
from scripts.common import run_with_driver, setup_logging

LOGGER = logging.getLogger("predict")

TARGET_PRECISION = 0.7
SUGGESTIONS_PER_CVE = 3
# "Clearly beats the baseline": at least this much higher precision@3 and a higher AUCPR on the test set.
GATE_PRECISION_MARGIN = 0.05
HAND_CHECK_SIZE = 20

# Reads every CVE once with its neighbours: O(CVEs + their CWE, AFFECTS and bridge relationships).
LOAD_QUERY = """
MATCH (c:CVE)
RETURN c.cve_id AS cve_id, toString(c.date_added) AS date_added, coalesce(c.name, '') AS name,
       c.cvss_score AS cvss_score, c.ssvc_exploitation AS ssvc_exploitation,
       c.ssvc_automatable AS ssvc_automatable, c.ssvc_technical_impact AS ssvc_technical_impact,
       coalesce(c.known_ransomware_use, false) AS ransomware,
       COLLECT { MATCH (c)-[:HAS_WEAKNESS]->(w:CWE) RETURN w.cwe_id } AS cwes,
       COLLECT { MATCH (c)-[:AFFECTS]->(p:Product) RETURN DISTINCT p.product_key } AS products,
       COLLECT { MATCH (c)-[:AFFECTS]->(:Product)-[:MADE_BY]->(v:Vendor) RETURN DISTINCT v.vendor_key } AS vendors,
       COLLECT { MATCH (c)-[:EXPLOITS_VIA|PRIMARY_IMPACT|SECONDARY_IMPACT]->(t:Technique)
                 RETURN DISTINCT t.attack_id } AS techniques
"""
TECHNIQUE_NAMES_QUERY = "MATCH (t:Technique) RETURN t.attack_id AS attack_id, t.name AS name"
# A prediction run fully replaces the previous one, so stale suggestions never survive a re-run.
DELETE_QUERY = "MATCH ()-[r:INFERRED_MAPS_TO]->() DELETE r"
# Both ends by index seek (cve_id, attack_id): O(log n) per suggestion.
STORE_QUERY = """
UNWIND $rows AS row
MATCH (c:CVE {cve_id: row.cve_id})
MATCH (t:Technique {attack_id: row.attack_id})
MERGE (c)-[r:INFERRED_MAPS_TO]->(t)
SET r.mapping_type = 'predicted', r.source = 'model', r.confidence = row.confidence, r.model = row.model,
    r.model_version = row.model_version, r.top_features = row.top_features, r.rationale = row.rationale,
    r.created_at = datetime()
"""
IMPORT_META_QUERY = """
MERGE (m:ImportMeta {source: 'predict'})
SET m.version = $model_version, m.status = $status, m.parameters = $parameters, m.metrics = $metrics,
    m.threshold = $threshold, m.suggestions = $suggestions, m.cves_with_suggestions = $cves,
    m.imported_at = datetime()
"""

REPORT_PATH = Path("processed") / "link_prediction_report.json"
NOT_STORED = "not stored: the model did not clearly beat the most-common-techniques baseline"


def load_cves(driver: Driver) -> tuple[list[lp.Cve], dict[str, str]]:
    """Read every KEV CVE with what the model may use, and the technique names for the report."""
    records, _, _ = driver.execute_query(LOAD_QUERY, routing_=RoutingControl.READ)
    names, _, _ = driver.execute_query(TECHNIQUE_NAMES_QUERY, routing_=RoutingControl.READ)
    cves = [lp.Cve(cve_id=r["cve_id"], date_added=r["date_added"], name=r["name"], cwes=frozenset(r["cwes"]),
                   products=frozenset(r["products"]), vendors=frozenset(r["vendors"]),
                   techniques=frozenset(r["techniques"]), cvss_score=r["cvss_score"],
                   ssvc_exploitation=r["ssvc_exploitation"], ssvc_automatable=r["ssvc_automatable"],
                   ssvc_technical_impact=r["ssvc_technical_impact"], known_ransomware_use=r["ransomware"])
            for r in records]
    return cves, {r["attack_id"]: r["name"] for r in names}


def hand_check_sample(test: list[lp.Cve], rows: lp.Rows, scores, technique_names: dict[str, str]) -> list[dict]:
    """The model's top suggestion for HAND_CHECK_SIZE test CVEs picked at random (seed 42), with what CTID
    actually says, for labelling by hand as plausible or implausible."""
    ranked = lp.ranked_by_cve(rows.keys, scores)
    picked = sorted(random.Random(42).sample(sorted(c.cve_id for c in test), min(HAND_CHECK_SIZE, len(test))))
    by_id = {c.cve_id: c for c in test}
    sample = []
    for cve_id in picked:
        technique, score = ranked[cve_id][0]
        sample.append({"cve_id": cve_id, "name": by_id[cve_id].name,
                       "suggested": f"{technique} {technique_names.get(technique, '')}".strip(),
                       "probability": round(score, 3), "matches_ctid": technique in by_id[cve_id].techniques,
                       "ctid": sorted(by_id[cve_id].techniques)})
    return sample


def _compare_models(rows: dict[str, lp.Rows], truth: dict[str, frozenset[str]]) -> tuple[dict, Any]:
    """Fit both models on train; score them and the baseline on validation and test."""
    metrics, forest = {}, None
    for kind in ("random_forest", "logistic_regression"):
        model = lp.make_model(kind).fit(rows["train"].x, rows["train"].y)
        forest = model if kind == "random_forest" else forest
        metrics[kind] = {split: lp.evaluate(rows[split], model.predict_proba(rows[split].x)[:, 1], truth)
                         for split in ("validation", "test")}
    metrics["popularity_baseline"] = {split: lp.evaluate(rows[split], lp.popularity_scores(rows[split]), truth)
                                      for split in ("validation", "test")}
    return metrics, forest


def _threshold_report(forest, rows: dict[str, lp.Rows], truth: dict[str, frozenset[str]]) -> dict | None:
    """Pick the threshold on validation, then say how it does on test."""
    threshold = lp.choose_threshold(rows["validation"].keys, forest.predict_proba(rows["validation"].x)[:, 1],
                                    truth, target_precision=TARGET_PRECISION)
    if threshold:
        kept = lp.select_suggestions(rows["test"].keys, forest.predict_proba(rows["test"].x)[:, 1],
                                     threshold["threshold"], SUGGESTIONS_PER_CVE)
        threshold["test_precision"] = (sum(t in truth[c] for c, t, _ in kept) / len(kept)) if kept else 0.0
        threshold["test_kept"] = len(kept)
    return threshold


def evaluation(cves: list[lp.Cve], technique_names: dict[str, str] | None = None) -> dict[str, Any]:
    """Train on the oldest mapped CVEs, pick the threshold on validation, report everything on test."""
    splits = dict(zip(("train", "validation", "test"), lp.temporal_split(cves)))
    reference = lp.Reference(splits["train"])
    rows = {name: lp.build_rows(split, reference) for name, split in splits.items()}
    truth = {c.cve_id: c.techniques for c in cves}
    metrics, forest = _compare_models(rows, truth)
    importance = permutation_importance(forest, rows["test"].x, rows["test"].y, scoring="average_precision",
                                        n_repeats=5, random_state=42)
    return {
        "split": {name: {"cves": len(split), "from": split[0].date_added, "to": split[-1].date_added}
                  for name, split in splits.items()},
        "candidate_techniques": len(reference.techniques),
        "models": metrics,
        "threshold": _threshold_report(forest, rows, truth),
        "feature_importance": sorted(
            ({"feature": name, "permutation_aucpr_drop": float(mean), "impurity": float(impurity)}
             for name, mean, impurity in zip(lp.FEATURES, importance.importances_mean,
                                             forest.feature_importances_)),
            key=lambda item: -item["permutation_aucpr_drop"]),
        "hand_check": hand_check_sample(splits["test"], rows["test"], forest.predict_proba(rows["test"].x)[:, 1],
                                        technique_names or {}),
    }


def passes_gate(report: dict[str, Any]) -> bool:
    """True if the random forest clearly beats the popularity baseline on the test set."""
    model, baseline = report["models"]["random_forest"]["test"], report["models"]["popularity_baseline"]["test"]
    return (model["precision_at_3"] >= baseline["precision_at_3"] + GATE_PRECISION_MARGIN
            and model["aucpr"] > baseline["aucpr"])


def model_version(cves: list[lp.Cve], threshold: float | None) -> str:
    """A short id for this exact model: same training CVEs, parameters and threshold give the same id."""
    mapped = sorted(c.cve_id for c in cves if c.techniques)
    digest = hashlib.sha256(json.dumps([mapped, lp.RANDOM_FOREST_PARAMS, threshold],
                                       sort_keys=True).encode()).hexdigest()[:10]
    return f"rf-{date.today().isoformat()}-{digest}"


def final_suggestions(cves: list[lp.Cve], threshold: float) -> list[dict[str, Any]]:
    """Refit on every mapped CVE and suggest techniques for the unmapped ones."""
    mapped = [c for c in cves if c.techniques]
    reference = lp.Reference(mapped)
    training = lp.build_rows(mapped, reference)
    forest = lp.make_model("random_forest").fit(training.x, training.y)
    targets = lp.build_rows([c for c in cves if not c.techniques], reference)
    scores = forest.predict_proba(targets.x)[:, 1]
    position = {key: i for i, key in enumerate(targets.keys)}
    means, version = training.x.mean(axis=0), model_version(cves, threshold)
    return [{"cve_id": cve_id, "attack_id": technique, "confidence": round(score, 4), "model": "random_forest",
             "model_version": version,
             "top_features": lp.top_features(forest, targets.x[position[(cve_id, technique)]], means),
             "rationale": lp.rationale(technique, targets.evidence[position[(cve_id, technique)]])}
            for cve_id, technique, score in lp.select_suggestions(targets.keys, scores, threshold,
                                                                  SUGGESTIONS_PER_CVE)]


def record_run(driver: Driver, version: str, status: str, rows: list[dict[str, Any]],
               report: dict[str, Any]) -> None:
    """Replace the stored suggestions with rows (possibly none) and record the run and its status."""
    driver.execute_query(DELETE_QUERY)
    run_batched(driver, STORE_QUERY, rows)
    driver.execute_query(IMPORT_META_QUERY, {
        "model_version": version,
        "status": status,
        "parameters": json.dumps({"random_forest": lp.RANDOM_FOREST_PARAMS, "features": lp.FEATURES,
                                  "target_precision": TARGET_PRECISION, "per_cve": SUGGESTIONS_PER_CVE,
                                  "gate_precision_margin": GATE_PRECISION_MARGIN}, sort_keys=True),
        "metrics": json.dumps(report["models"], sort_keys=True),
        "threshold": (report["threshold"] or {}).get("threshold"),
        "suggestions": len(rows),
        "cves": len({row["cve_id"] for row in rows}),
    })


def log_report(report: dict[str, Any]) -> None:
    """Print the evaluation in a readable form."""
    for name, split in report["split"].items():
        LOGGER.info("split %-10s %3d CVEs  %s .. %s", name, split["cves"], split["from"], split["to"])
    for model, splits in report["models"].items():
        for split, metrics in splits.items():
            LOGGER.info("%-20s %-10s AUCPR %.3f  P@3 %.3f  R@3 %.3f", model, split, metrics["aucpr"],
                        metrics["precision_at_3"], metrics["recall_at_3"])
    LOGGER.info("threshold: %s", report["threshold"])
    for item in report["feature_importance"]:
        LOGGER.info("importance %-26s permutation %.4f  impurity %.3f", item["feature"],
                    item["permutation_aucpr_drop"], item["impurity"])


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Suggest techniques for unmapped KEV CVEs (D18).")
    parser.add_argument("--evaluate-only", action="store_true", help="report the evaluation, change nothing")
    parser.add_argument("--force", action="store_true", help="store even if the model fails the baseline gate")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Evaluate, gate, and record the outcome. Returns 0 when the run completed (whether or not the gate
    let suggestions through) and 1 on errors."""
    args = parse_args(argv)
    settings = setup_logging()
    loaded = run_with_driver(load_cves, LOGGER)
    if not loaded or not loaded[0]:
        LOGGER.error("no CVEs loaded: run make ingest first")
        return 1
    cves, technique_names = loaded
    report = evaluation(cves, technique_names)
    log_report(report)
    report_path = settings.data_dir / REPORT_PATH
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOGGER.info("evaluation written to %s", report_path)
    if args.evaluate_only:
        return 0

    threshold = (report["threshold"] or {}).get("threshold")
    if threshold is not None and (passes_gate(report) or args.force):
        rows = final_suggestions(cves, threshold)
        status = "stored" if passes_gate(report) else "stored with --force: the model did not pass the gate"
    else:
        rows, status = [], NOT_STORED if threshold is not None else (
            f"not stored: no threshold reaches {TARGET_PRECISION:.0%} precision on validation")
        LOGGER.warning("%s; previous suggestions removed", status)
    version = model_version(cves, threshold)
    if run_with_driver(lambda driver: record_run(driver, version, status, rows, report) or True, LOGGER) is None:
        return 1
    LOGGER.info("%s: %d suggestions for %d CVEs (model %s)", status, len(rows),
                len({r["cve_id"] for r in rows}), version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
