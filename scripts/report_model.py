"""Write docs/model_report.md and docs/figures/calibration.png from a training run."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

# pylint: disable=wrong-import-position
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve

from app.ml import features as F

DOC = Path("docs/model_report.md")
FIGURE = Path("docs/figures/calibration.png")
BINS = 10
# Categorical slots 1-4 of the reference palette (validated: CVD and normal-vision separation pass;
# aqua and yellow are below 3:1 on the surface, so every series also gets a marker shape, a legend
# entry and the calibration table printed under the figure).
SERIES = {
    "Graph model": ("#2a78d6", "o"),
    "Pinnacle (no margin)": ("#eb6834", "s"),
    "Bet365 (no margin)": ("#1baf7a", "^"),
    "Ranking baseline": ("#eda100", "D"),
}
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"


def table(rows: dict[str, dict], first: str = "Predictor") -> str:
    """Markdown table from {name: {metric: value}}."""
    metrics = ["logLoss", "brier", "accuracy", "n"]
    lines = [f"| {first} | Log loss | Brier | Accuracy | Rows |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, values in rows.items():
        lines.append(f"| {name} | " + " | ".join(str(values[m]) for m in metrics) + " |")
    return "\n".join(lines)


def calibration_bins(labels, probabilities: dict) -> dict[str, tuple]:
    """(mean predicted, observed frequency) per quantile bin for each predictor."""
    curves = {}
    for name, p in probabilities.items():
        observed, predicted = calibration_curve(labels, p, n_bins=BINS, strategy="quantile")
        curves[name] = (predicted, observed)
    return curves


def plot_calibration(curves: dict[str, tuple], rows: int) -> None:
    """Reliability diagram: one line per predictor against the diagonal of perfect calibration."""
    FIGURE.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 6.0), dpi=150, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ax.plot([0, 1], [0, 1], color=MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.text(0.03, 0.08, "perfect calibration", color=MUTED, fontsize=8, ha="left", rotation=40)
    for name, (predicted, observed) in curves.items():
        color, marker = SERIES[name]
        ax.plot(predicted, observed, color=color, linewidth=2, marker=marker, markersize=6,
                markeredgecolor=SURFACE, markeredgewidth=1.5, label=name, zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Predicted probability that p1 wins (quantile bins)", color=MUTED, fontsize=9)
    ax.set_ylabel("Observed share of p1 wins", color=MUTED, fontsize=9)
    ax.set_title(f"Calibration on the test seasons ({rows:,} matches priced by both bookmakers)",
                 color=INK, fontsize=10, loc="left")
    ax.grid(color=GRID, linewidth=0.8)
    ax.tick_params(colors=MUTED, labelsize=8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper left", labelcolor=INK)
    fig.tight_layout()
    fig.savefig(FIGURE, facecolor=SURFACE)
    plt.close(fig)


def calibration_table(curves: dict[str, tuple]) -> str:
    """Text version of the figure (bin means per predictor)."""
    lines = ["| Predictor | Predicted (bin mean) -> observed |", "| --- | --- |"]
    for name, (predicted, observed) in curves.items():
        pairs = ", ".join(f"{p:.2f}->{o:.2f}" for p, o in zip(predicted, observed))
        lines.append(f"| {name} | {pairs} |")
    return "\n".join(lines)


def coefficient_table(artifact: dict) -> str:
    """Standardised weights of the scalar features, largest first (FastRP summarised)."""
    weights = artifact["standardisedWeights"]
    scalar = sorted(((n, weights[n]) for n in F.SCALAR_FEATURES), key=lambda item: abs(item[1]), reverse=True)
    fastrp = [abs(weights[n]) for n in F.EMBEDDING_FEATURES]
    lines = ["| Feature (p1 - p2) | Weight per standard deviation |", "| --- | ---: |"]
    lines += [f"| {name} | {value:+.3f} |" for name, value in scalar]
    lines.append(f"| fastrp00..63 (64 dims) | mean abs {np.mean(fastrp):.3f}, max abs {max(fastrp):.3f} |")
    return "\n".join(lines)


def reading_notes(dataset: pd.DataFrame, result: dict) -> str:
    """Facts needed to read the tables: gaps to the market and the collinear PageRank pair."""
    train = dataset[dataset["split"] == "train"]
    correlation = train["logPrestige"].corr(train["logRecentPrestige"])
    common = result["common"]
    gap_market = common["Graph model"]["logLoss"] - common["Pinnacle (no margin)"]["logLoss"]
    gap_rank = common["Graph model"]["logLoss"] - common["Ranking baseline"]["logLoss"]
    return "\n".join([
        f"- Log loss gap to Pinnacle: {gap_market:+.4f}; to the ranking baseline: {gap_rank:+.4f} (positive = worse).",
        f"- logPrestige and logRecentPrestige are correlated (r = {correlation:.2f} on train), so their weights"
        + " are not interpretable one by one: together they reward recent prestige and penalise a career"
        + " prestige that recent results no longer support.",
        "- The ranking baseline uses ATP ranks, which summarise 52 weeks of results at every level"
        + " (Challengers, qualifying) that are not in this graph; the graph model sees tour-level matches only.",
    ])

def write(dataset: pd.DataFrame, chosen: dict, candidates: list[dict], result: dict, artifact: dict) -> None:
    """Assemble the Markdown report and the figure."""
    curves = calibration_bins(result["calibration"]["labels"], result["calibration"]["probabilities"])
    plot_calibration(curves, len(result["calibration"]["labels"]))
    splits = dataset.groupby("split").agg(rows=("label", "size"), p1WonRate=("label", "mean"),
                                         first=("date", "min"), last=("date", "max"))
    validation = {
        (f"{c['model']} C={c['C']}" if c["C"] is not None else c["model"]): c for c in candidates
    }
    first, last = result["seasons"]
    lines = [
        "# Match-outcome model report",
        "",
        f"Generated by `make train` (`scripts/train.py`). Model `{artifact['version']}`.",
        "",
        "## Data and split",
        "",
        "One row per played match (walkovers excluded) from 1995; p1/p2 assigned by a seeded coin flip per "
        + "match; label = p1 won. Features are p1 - p2 differences computed only from matches before the "
        + "match (graph snapshot at Jan 1 of its season; history strictly before its date).",
        "",
        "| Split | Rows | p1 won rate | First match | Last match |",
        "| --- | ---: | ---: | --- | --- |",
        *[f"| {s} | {r.rows:,} | {r.p1WonRate:.4f} | {r.first} | {r.last} |" for s, r in splits.iterrows()],
        "",
        "## Model selection (validation 2019-2021 only)",
        "",
        table(validation, "Candidate"),
        "",
        f"Chosen: **{chosen['model']}**" + (f" with C = {chosen['C']}" if chosen.get("C") is not None else "")
        + ". Gradient boosting is kept only if it improves validation log loss by at least 1%. "
        + "The chosen model is refitted on train + validation before the test.",
        "",
        f"## Test ({first}-{last}, evaluated once)",
        "",
        "Same rows for every predictor: completed matches (no walkover, no retirement) priced by both "
        + "Pinnacle and Bet365. Bookmaker probabilities have the margin removed: (1/o1) / (1/o1 + 1/o2). "
        + "The ranking baseline is a one-feature logistic model on log(rank p2 / rank p1), fitted on train.",
        "",
        table(result["common"]),
        "",
        "Retired matches (same predictors, reported separately):",
        "",
        table(result["retired"]),
        "",
        "Graph model on every completed test match (with or without odds): log loss "
        + f"{result['allCompleted']['logLoss']}, accuracy {result['allCompleted']['accuracy']} "
        + f"({result['allCompleted']['n']:,} rows).",
        "",
        "## Calibration (test, common rows)",
        "",
        f"![Calibration]({FIGURE.relative_to('docs').as_posix()})",
        "",
        calibration_table(curves),
        "",
        "## What the model uses",
        "",
        coefficient_table(artifact),
        "",
        reading_notes(dataset, result),
        "",
    ]
    DOC.write_text("\n".join(lines), encoding="utf-8", newline="\n")
