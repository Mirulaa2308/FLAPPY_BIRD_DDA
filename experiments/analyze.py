"""Analyze experiment results and print a summary table.

Run from project root:
    python -m experiments.analyze
"""
import csv
import os
import statistics
from collections import defaultdict


RESULTS_PATH = "data/experiment_results.csv"


def load():
    with open(RESULTS_PATH) as f:
        return list(csv.DictReader(f))


def summarize(rows):
    # Group by (bot, controller)
    groups = defaultdict(list)
    for r in rows:
        key = (r["bot"], r["controller"])
        groups[key].append(r)

    print(f"\n{'Bot':8s} {'Controller':14s} {'AvgScore':>9s} {'AvgSurv(s)':>11s} "
          f"{'Oscillation':>12s} {'MeanGap':>8s} {'MinGap':>7s} {'MaxGap':>7s}")
    print("-" * 80)

    for bot in ["low", "medium", "high"]:
        for ctrl in ["fixed", "reactive", "ml_adaptive"]:
            rs = groups.get((bot, ctrl), [])
            if not rs:
                continue
            avg_score = statistics.mean(float(r["score"]) for r in rs)
            avg_surv = statistics.mean(float(r["survival_time_s"]) for r in rs)
            avg_osc = statistics.mean(float(r["difficulty_oscillation"]) for r in rs)
            mean_gap = statistics.mean(float(r["mean_gap"]) for r in rs)
            min_gap = min(float(r["min_gap"]) for r in rs)
            max_gap = max(float(r["max_gap"]) for r in rs)
            print(f"{bot:8s} {ctrl:14s} {avg_score:9.2f} {avg_surv:11.2f} "
                  f"{avg_osc:12.1f} {mean_gap:8.1f} {min_gap:7.1f} {max_gap:7.1f}")

    # Cross-bot comparison: which controller produces the widest spread
    # of outcome quality (i.e., is more adaptive)?
    print("\nController comparison (averaged across all bots):")
    print(f"{'Controller':14s} {'AvgScore':>9s} {'Oscillation':>12s} {'MeanGap':>8s}")
    print("-" * 48)
    for ctrl in ["fixed", "reactive", "ml_adaptive"]:
        rs = [r for r in rows if r["controller"] == ctrl]
        avg_score = statistics.mean(float(r["score"]) for r in rs)
        avg_osc = statistics.mean(float(r["difficulty_oscillation"]) for r in rs)
        mean_gap = statistics.mean(float(r["mean_gap"]) for r in rs)
        print(f"{ctrl:14s} {avg_score:9.2f} {avg_osc:12.1f} {mean_gap:8.1f}")


def make_plot(rows):
    """Bar chart: avg score per controller (single-bot experiment)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("\n[analyze] matplotlib not installed; skipping plot.")
        return

    groups = defaultdict(list)
    for r in rows:
        groups[r["controller"]].append(float(r["score"]))

    controllers = ["fixed", "reactive", "ml_adaptive"]
    colors = ["#3b82f6", "#f59e0b", "#10b981"]

    means = [statistics.mean(groups[c]) for c in controllers]
    stds = [statistics.pstdev(groups[c]) for c in controllers]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(controllers))
    ax.bar(x, means, yerr=stds, color=colors, capsize=5)
    ax.set_xticks(x)
    ax.set_xticklabels(controllers)
    ax.set_ylabel("Average pipes passed per episode")
    ax.set_title("FLAPPY ADAPT: Score by difficulty controller\n(high-skill bot, 10 episodes each)")
    ax.grid(axis="y", alpha=0.3)

    os.makedirs("data/plots", exist_ok=True)
    out = "data/plots/score_comparison.png"
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    print(f"\nSaved plot to {out}")

if __name__ == "__main__":
    rows = load()
    print(f"Loaded {len(rows)} episodes")
    summarize(rows)
    make_plot(rows)