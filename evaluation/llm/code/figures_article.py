#!/usr/bin/env python3
"""Figures 2-7 de la section, en anglais, a partir de article/valeurs.json."""
import json, pathlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

ICI = pathlib.Path(__file__).resolve().parent
V = json.load(open(ICI / "article" / "valeurs.json", encoding="utf-8"))
OUT = ICI / "article" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK, INK2, MUTED, GRID, SURF = "#1f1f1e", "#55544f", "#8c8b85", "#e4e3de", "#ffffff"
GREY = "#a9a8a2"
COL = {"M1": "#2a78d6", "M2": "#eb6834", "M3": "#1baf7a", "Ens": "#eda100"}
LLM = ["meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct", "deepseek/deepseek-chat"]
NOM = {LLM[0]: "M1 Llama 3.3 70B", LLM[1]: "M2 Qwen 2.5 72B", LLM[2]: "M3 DeepSeek-V3",
       "ensemble": "Ensemble"}
CLE = {LLM[0]: "M1", LLM[1]: "M2", LLM[2]: "M3", "ensemble": "Ens"}

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "savefig.bbox": "tight"})


def habiller(ax, grille_y=True):
    ax.set_axisbelow(True)
    if grille_y:
        ax.yaxis.grid(True, color=GRID, linewidth=0.7)
    ax.tick_params(length=0)


def save(fig, nom):
    fig.savefig(OUT / f"{nom}.pdf")
    fig.savefig(OUT / f"{nom}.png", dpi=300)
    plt.close(fig)


T2 = V["table2"]


def ligne(m):
    return T2[f"{m}|original"]


# ---- Figure 2 : quatre metriques, small multiples -------------------------
methodes = [("baseline/majoritaire", "Majority", GREY), ("baseline/aleatoire", "Random", GREY),
            ("baseline/lexical", "Lexical", GREY)] + \
           [(m, NOM[m].split(" ", 1)[0], COL[CLE[m]]) for m in LLM] + [("ensemble", "Ens.", COL["Ens"])]
metr = [("balanced_accuracy", "Balanced accuracy"), ("f1_macro", "Macro-F1"),
        ("MCC", "MCC"), ("kappa_cohen", "Cohen's $\\kappa$")]
fig, axes = plt.subplots(1, 4, figsize=(7.0, 2.3), sharey=True)
for ax, (k, titre) in zip(axes, metr):
    for i, (m, lab, c) in enumerate(methodes):
        v = ligne(m)[k]
        ax.bar(i, v, 0.72, color=c, edgecolor=SURF, linewidth=1.2, zorder=3)
        if i >= 2:   # les references triviales (0 par construction) sont dans la Table 2
            ax.annotate(f"{v:.2f}", (i, max(v, 0)), xytext=(0, 2), textcoords="offset points",
                        ha="center", va="bottom", fontsize=5.6, color=INK)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.axvline(2.5, color=GRID, linewidth=1, linestyle=(0, (2, 2)))
    ax.set_xticks(range(len(methodes)))
    ax.set_xticklabels([m[1] for m in methodes], rotation=60, ha="right", fontsize=6.5)
    ax.set_title(titre, fontsize=8, color=INK)
    ax.set_ylim(-0.15, 1.05)
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    habiller(ax)
axes[0].set_ylabel("score (original vocabulary, $n=51$)")
save(fig, "fig2_methods")

# ---- Figure 3 : forest MCC et macro-F1 ------------------------------------
rang = ["baseline/lexical"] + LLM + ["ensemble"]
labs = ["Lexical baseline"] + [NOM[m] for m in LLM] + ["Ensemble"]
fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.0), sharey=True)
for ax, (k, lo, hi, titre, ref) in zip(axes, [("MCC", "mcc_ic95_bas", "mcc_ic95_haut", "MCC", 0.0),
                                              ("f1_macro", "f1_ic95_bas", "f1_ic95_haut", "Macro-F1", 0.4333)]):
    for j, m in enumerate(rang):
        r = ligne(m)
        y = len(rang) - 1 - j
        c = GREY if m.startswith("baseline") else COL[CLE[m]]
        ax.plot([r[lo], r[hi]], [y, y], color=c, linewidth=2, solid_capstyle="round", zorder=3)
        ax.scatter([r[k]], [y], s=34, color=c, edgecolor=SURF, linewidth=1.5, zorder=4)
        ax.annotate(f"{r[k]:.2f} [{r[lo]:.2f}, {r[hi]:.2f}]", (r[hi], y), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=6.3, color=INK2)
    ax.axvline(ref, color=MUTED, linewidth=0.9, linestyle=(0, (4, 3)))
    ax.set_yticks(range(len(rang)))
    ax.set_yticklabels(labs[::-1])
    ax.set_xlim(-0.3, 1.25) if k == "MCC" else ax.set_xlim(0.2, 1.2)
    ax.set_title(f"{titre}, 95% BCa interval", fontsize=8, color=INK)
    ax.xaxis.grid(True, color=GRID, linewidth=0.7); ax.set_axisbelow(True); ax.tick_params(length=0)
save(fig, "fig3_forest")

# ---- Figure 4 : strates -----------------------------------------------------
T4 = V["table4"]
strates = [("A", "Mod. A"), ("B", "Mod. B"), ("C", "Mod. C"), ("D", "Mod. D"), ("E", "Mod. E"),
           ("F", "Mod. F"), ("cross", "Cross"), ("simple", "Simple"), ("complex", "Complex")]
fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.2), sharey=True)
for ax, (k, titre) in zip(axes, [("precision", "Precision"), ("recall", "Recall"), ("f1_macro", "Macro-F1")]):
    for i, (s, lab) in enumerate(strates):
        v = T4[s][k]
        ax.bar(i, v, 0.7, color=COL["Ens"], edgecolor=SURF, linewidth=1.2, zorder=3)
        ax.annotate(f"{v:.2f}", (i, v), xytext=(0, -3), textcoords="offset points", ha="center",
                    va="top", rotation=90, fontsize=5.6, color=INK)
    ax.axvline(6.5, color=MUTED, linewidth=0.9, linestyle=(0, (2, 2)))
    ax.set_xticks(range(len(strates))); ax.set_xticklabels([s[1] for s in strates], rotation=60, ha="right")
    ax.set_title(titre, fontsize=8, color=INK); ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_locator(MultipleLocator(0.25)); habiller(ax)
axes[0].set_ylabel("ensemble verdict, original vocabulary")
save(fig, "fig4_strata")

# ---- Figure 5 : detection par force d'ablation ------------------------------
T5 = V["table5"]
fig, ax = plt.subplots(figsize=(6.2, 2.4))
mods = LLM + ["ensemble"]
w = 0.19
for j, m in enumerate(mods):
    xs, ys, lo, hi = [], [], [], []
    for i, c in enumerate(["A1", "A2", "A3"]):
        r = T5[f"{m}|original|{c}"]
        x = i + (j - 1.5) * w
        xs.append(x); ys.append(r["rate"]); lo.append(r["rate"] - r["wilson"][0]); hi.append(r["wilson"][1] - r["rate"])
        ax.annotate(f"{r['det']}/{r['n']}", (x, r["wilson"][1]), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=5.8, color=INK2)
    ax.bar(xs, ys, w * 0.9, color=COL[CLE[m]], edgecolor=SURF, linewidth=1.2, label=NOM[m], zorder=3)
    ax.errorbar(xs, ys, yerr=[lo, hi], fmt="none", ecolor=INK2, elinewidth=0.8, capsize=2, zorder=4)
ax.axhline(0.5, color=MUTED, linewidth=0.9, linestyle=(0, (4, 3)))
ax.annotate("chance", (-0.5, 0.5), xytext=(0, 2), textcoords="offset points", fontsize=6.5, color=MUTED, ha="left")
ax.set_xlim(-0.55, 2.55)
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["A1 element removal", "A2 relation rewiring", "A3 near-miss substitution"])
ax.set_ylim(0, 1.18); ax.set_ylabel("detection rate (95% Wilson)")
ax.yaxis.set_major_locator(MultipleLocator(0.25)); habiller(ax)
ax.legend(ncol=4, fontsize=6.5, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.16))
save(fig, "fig5_ablation")

# ---- Figure 6 : MCC par execution -------------------------------------------
R = V["runs"]
fig, ax = plt.subplots(figsize=(4.6, 2.3))
for m in LLM:
    pts = R[m]["original"]["par_run"]
    xs = [p["k"] for p in pts]; ys = [p["MCC"] for p in pts]
    ax.plot(xs, ys, color=COL[CLE[m]], linewidth=2, marker="o", markersize=5,
            markeredgecolor=SURF, markeredgewidth=1.2, zorder=3)
    ax.annotate(NOM[m], (xs[-1], ys[-1]), xytext=(6, 0), textcoords="offset points", va="center",
                fontsize=6.5, color=INK2)
ax.set_xticks([1, 2, 3]); ax.set_xlim(0.8, 3.9); ax.set_ylim(0, 1)
ax.set_xlabel("independent run $k$ ($K=3$)"); ax.set_ylabel("MCC (original vocabulary)")
ax.yaxis.set_major_locator(MultipleLocator(0.25)); habiller(ax)
save(fig, "fig6_runs")

# ---- Figure 7 : fiabilite de la confiance declaree --------------------------
C = V["calibration"]
fig, ax = plt.subplots(figsize=(5.2, 2.4))
niv = ["low", "medium", "high"]; nominal = {"low": 0.25, "medium": 0.6, "high": 0.9}
for j, m in enumerate(LLM):
    for i, nv in enumerate(niv):
        d = C[m]["niveaux"].get(nv)
        x = i + (j - 1) * 0.25
        if not d:
            ax.annotate("n=0", (x, 0.02), ha="center", fontsize=5.5, color=MUTED)
            continue
        ax.bar(x, d["acc"], 0.23, color=COL[CLE[m]], edgecolor=SURF, linewidth=1.2, zorder=3,
               label=f"{NOM[m]} (ECE {C[m]['ECE']:.3f})" if nv == "high" else None)
        ax.annotate(f"n={d['n']}", (x, d["acc"]), xytext=(0, 2), textcoords="offset points",
                    ha="center", fontsize=5.5, color=INK2, zorder=6,
                    bbox=dict(boxstyle="square,pad=0.1", fc=SURF, ec="none"))
for i, nv in enumerate(niv):
    ax.plot([i - 0.42, i + 0.42], [nominal[nv]] * 2, color=INK, linewidth=1, linestyle=(0, (4, 2)), zorder=5)
ax.set_xticks([0, 1, 2]); ax.set_xticklabels(["Low (0.25)", "Medium (0.60)", "High (0.90)"])
ax.set_xlabel("self-reported confidence (nominal value)"); ax.set_ylabel("run-level accuracy")
ax.set_ylim(0, 1.15); ax.yaxis.set_major_locator(MultipleLocator(0.25)); habiller(ax)
ax.legend(fontsize=6.3, frameon=False, loc="upper left")
save(fig, "fig7_calibration")
print("figures ->", OUT)
