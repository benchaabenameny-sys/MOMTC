#!/usr/bin/env python3
"""Figures de la section validation, en PDF vectoriel pour LaTeX et en PNG.

Regles suivies, et leurs raisons :

- Palette categorielle de trois teintes validee pour les daltonismes
  (deuteranopie, protanopie, tritanopie) : ecart minimal toutes paires
  dE 9,2 en OKLab, plancher vision normale 24,0. Au-dela de trois series il
  faudrait des petits multiples, pas une quatrieme teinte.
- Chaque barre porte sa valeur en clair. La couleur ne transporte jamais seule
  une information : une figure d'article doit rester lisible imprimee en noir
  et blanc.
- Un seul axe par figure. Jamais deux echelles verticales.
- Les intervalles de confiance sont dessines partout ou ils existent. Une barre
  sans intervalle laisse croire a une precision qu'on n'a pas.
- La ligne MCC = 0 est tracee et legendee : c'est le niveau d'un juge sans
  information, et c'est la lecture la plus importante de la figure 1.
- Chaque figure est accompagnee d'un CSV de memes chiffres, pour qui veut la
  table plutot que l'image.

Usage :
    python figures.py --metriques metriques_exploitable.csv --tests tests.csv
"""
import argparse, csv, math, pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

SURFACE = "#fcfcfb"
ENCRE = "#0b0b0b"
ENCRE_2 = "#52514e"
GRILLE = "#e3e2de"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]     # slots 1-3, valides toutes paires
NEUTRE = "#8a8984"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.size": 9,
    "axes.edgecolor": GRILLE, "axes.labelcolor": ENCRE,
    "xtick.color": ENCRE_2, "ytick.color": ENCRE_2,
    "axes.titlecolor": ENCRE, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlepad": 24,
    "legend.frameon": False, "figure.dpi": 150,
    "font.family": ["DejaVu Sans"],
})

SORTIE = pathlib.Path("figures")


def habiller(ax, titre, sous_titre=None, ylabel=None):
    ax.set_title(titre)
    if sous_titre:
        # sous le titre, jamais dessus : le titre est decale par titlepad
        ax.text(0, 1.015, sous_titre, transform=ax.transAxes, fontsize=8,
                color=ENCRE_2, va="bottom")
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=8.5, color=ENCRE_2)
    for bord in ("top", "right"):
        ax.spines[bord].set_visible(False)
    ax.spines["left"].set_color(GRILLE)
    ax.spines["bottom"].set_color(GRILLE)
    ax.yaxis.grid(True, color=GRILLE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def plafonner(fig):
    """Retire les graduations au-dessus de 1 : MCC et proportions n'y vont
    jamais, et un repere qui annonce une valeur inatteignable induit en
    erreur. L'espace au-dessus reste, pour la legende et les valeurs."""
    for ax in fig.axes:
        bas, haut = ax.get_ylim()
        if haut > 1.0:
            ax.set_yticks([t for t in ax.get_yticks() if bas <= t <= 1.0001])
            ax.set_ylim(bas, haut)


def enregistrer(fig, nom, lignes_table=None, entetes=None):
    plafonner(fig)
    SORTIE.mkdir(exist_ok=True)
    for ext in ("pdf", "png"):
        fig.savefig(SORTIE / f"{nom}.{ext}", bbox_inches="tight",
                    dpi=300 if ext == "png" else None)
    plt.close(fig)
    if lignes_table:
        with open(SORTIE / f"{nom}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(entetes); w.writerows(lignes_table)
    print(f"  figures/{nom}.pdf · .png" + ("  · .csv" if lignes_table else ""))


def court(nom):
    """Nom de modele abrege pour les axes, sans perdre la famille."""
    n = nom.split("/")[-1]
    return n[:22]


def f(v, defaut=float("nan")):
    try:
        return float(v)
    except (TypeError, ValueError):
        return defaut


# --------------------------------------------------------------------------
def ordre_modeles(noms):
    """References d'abord (plancher), puis les modeles, puis l'ensemble :
    l'ordre de lecture de la Figure 2 du protocole."""
    ref = [m for m in ("baseline/majoritaire", "baseline/aleatoire", "baseline/lexical") if m in noms]
    llm = sorted(m for m in noms if not m.startswith("baseline/") and m != "ensemble")
    return ref + llm + (["ensemble"] if "ensemble" in noms else []), len(ref)


def fig1_mcc(rangs):
    """MCC par modele et par lexique, avec IC95 BCa."""
    modeles, n_ref = ordre_modeles({r["modele"] for r in rangs})
    lexiques = [l for l in ("original", "renomme", "renomme_q")
                if any(r["lexique"] == l for r in rangs)]
    etiq = {"original": "vocabulaire d'origine", "renomme": "fragment renomme",
            "renomme_q": "question et fragment renommes"}

    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    largeur = 0.72 / len(lexiques)
    table = []
    for j, lex in enumerate(lexiques):
        xs, ys, bas, haut = [], [], [], []
        for i, m in enumerate(modeles):
            r = next((x for x in rangs if x["modele"] == m and x["lexique"] == lex), None)
            if not r:
                continue
            v = f(r["MCC"])
            xs.append(i + (j - (len(lexiques) - 1) / 2) * largeur)
            ys.append(v)
            bas.append(max(0, v - f(r["mcc_ic95_bas"])))
            haut.append(max(0, f(r["mcc_ic95_haut"]) - v))
            table.append([m, lex, r["n"], f"{v:.3f}",
                          f"{f(r['mcc_ic95_bas']):.3f}", f"{f(r['mcc_ic95_haut']):.3f}"])
        ax.bar(xs, ys, largeur * 0.92, label=etiq[lex], color=SERIES[j],
               edgecolor=SURFACE, linewidth=1.4, zorder=3)
        ax.errorbar(xs, ys, yerr=[bas, haut], fmt="none", ecolor=ENCRE_2,
                    elinewidth=1.1, capsize=3, zorder=4)
        # la valeur se pose au-dessus de la moustache haute, pas de la barre,
        # sinon elle chevauche le capuchon de l'intervalle
        for x, y, h in zip(xs, ys, haut):
            ax.annotate(f"{y:.2f}", (x, y + h), textcoords="offset points",
                        xytext=(0, 4), ha="center", fontsize=8, color=ENCRE)

    ax.axhline(0, color=NEUTRE, linewidth=1.2, linestyle=(0, (4, 3)), zorder=2)
    ax.set_xticks(range(len(modeles)))
    ax.set_xticklabels([court(m) for m in modeles])
    bas_axe = min(-0.3, min(f(r["mcc_ic95_bas"]) for r in rangs
                            if r["lexique"] in lexiques) - 0.12)
    ax.set_ylim(bas_axe, 1.30)
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    if 0 < n_ref < len(modeles):
        ax.axvline(n_ref - 0.5, color=GRILLE, linewidth=1.2, linestyle=(0, (2, 2)), zorder=1)
        bas = ax.get_ylim()[0]
        ax.text(n_ref / 2 - 0.5, bas + 0.03, "references", ha="center", va="bottom",
                fontsize=7.5, color=ENCRE_2, style="italic")
        ax.text((n_ref + len(modeles)) / 2 - 0.5, bas + 0.03, "modeles de langage",
                ha="center", va="bottom", fontsize=7.5, color=ENCRE_2, style="italic")
    habiller(ax, "Coefficient de correlation de Matthews par modele",
             "IC95 bootstrap BCa sur les items  ·  pointille horizontal : MCC = 0, juge sans information",
             "MCC")
    ax.legend(loc="upper center", fontsize=8.5, ncol=len(lexiques),
              bbox_to_anchor=(0.5, 1.0))
    enregistrer(fig, "fig1_mcc_par_modele", table,
                ["modele", "lexique", "n", "MCC", "ic95_bas", "ic95_haut"])


def fig2_conditions(rangs):
    """Taux de detection par condition d'ablation, avec IC de Wilson."""
    conds = ["A1", "A2", "A3"]
    noms = {"A1": "A1  suppression", "A2": "A2  recablage",
            "A3": "A3  quasi-correspondance"}
    modeles = sorted({r["modele"] for r in rangs if r["lexique"] in conds})
    if not modeles:
        return
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    largeur = 0.26
    table = []
    for j, m in enumerate(modeles):
        xs, ys, bas, haut = [], [], [], []
        for i, c in enumerate(conds):
            r = next((x for x in rangs if x["modele"] == m and x["lexique"] == c), None)
            if not r:
                continue
            v = f(r["accuracy"])
            xs.append(i + (j - (len(modeles) - 1) / 2) * largeur)
            ys.append(v)
            bas.append(max(0, v - f(r["acc_ic95_bas"])))
            haut.append(max(0, f(r["acc_ic95_haut"]) - v))
            table.append([m, c, r["n"], f"{v:.3f}",
                          f"{f(r['acc_ic95_bas']):.3f}", f"{f(r['acc_ic95_haut']):.3f}"])
        ax.bar(xs, ys, largeur * 0.9, label=court(m), color=SERIES[j % 3],
               edgecolor=SURFACE, linewidth=1.4, zorder=3)
        ax.errorbar(xs, ys, yerr=[bas, haut], fmt="none", ecolor=ENCRE_2,
                    elinewidth=1.1, capsize=3, zorder=4)
        for x, y, h in zip(xs, ys, haut):
            ax.annotate(f"{y:.2f}", (x, y + h), textcoords="offset points",
                        xytext=(0, 4), ha="center", fontsize=7.5, color=ENCRE)
    ax.set_xticks(range(len(conds)))
    ax.set_xticklabels([noms[c] for c in conds])
    ax.set_ylim(0, 1.24)
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    habiller(ax, "Detection des negatifs selon le type d'ablation",
             "part des items ablates correctement rejetes · IC95 de Wilson",
             "taux de detection")
    ax.legend(loc="upper right", fontsize=8.5, ncol=len(modeles))
    enregistrer(fig, "fig2_detection_par_condition", table,
                ["modele", "condition", "n", "taux", "ic95_bas", "ic95_haut"])


def fig3_sens_spec(rangs):
    """Sensibilite contre specificite : ou se situe le juge complaisant."""
    pts = [r for r in rangs if r["lexique"] in ("original", "renomme", "renomme_q")]
    if not pts:
        return
    fig, ax = plt.subplots(figsize=(6.4, 5.2))

    # sensibilite + specificite = 1 : balanced accuracy de 0,5, soit la
    # performance d'un juge qui n'apporte aucune information. Tout point sur
    # cette droite est sans valeur, quelle que soit son accuracy apparente.
    ax.plot([0, 1], [1, 0], color=NEUTRE, linewidth=1,
            linestyle=(0, (4, 3)), zorder=1)
    ax.annotate("balanced accuracy = 0,5 : aucune information apportee",
                (0.52, 0.49), fontsize=7.5, color=ENCRE_2, rotation=-34,
                rotation_mode="anchor", ha="left", va="bottom", zorder=2)

    modeles = sorted({r["modele"] for r in pts})
    marqueurs = {"original": "o", "renomme": "^", "renomme_q": "s"}

    # Deux conditions peuvent tomber exactement au meme endroit (un modele qui
    # repond oui partout, par exemple). On empile alors les etiquettes au lieu
    # de les superposer.
    occupe = {}
    table = []
    for r in sorted(pts, key=lambda r: (r["modele"], r["lexique"])):
        i = modeles.index(r["modele"])
        x, y = f(r["sensibilite"]), f(r["specificite"])
        ax.scatter([x], [y], s=84, color=SERIES[i % 3], marker=marqueurs[r["lexique"]],
                   edgecolor=SURFACE, linewidth=1.6, zorder=4)
        cle = (round(x, 2), round(y, 2))
        rang = occupe.get(cle, 0)
        occupe[cle] = rang + 1
        droite = x < 0.93
        ax.annotate(f"{court(r['modele'])} · {r['lexique']}", (x, y),
                    textcoords="offset points",
                    xytext=(9 if droite else -9, 4 - rang * 11),
                    ha="left" if droite else "right",
                    fontsize=7.5, color=ENCRE_2, zorder=5)
        table.append([r["modele"], r["lexique"], f"{x:.3f}", f"{y:.3f}"])

    ax.set_xlim(0.42, 1.06); ax.set_ylim(-0.12, 1.10)
    ax.xaxis.set_major_locator(MultipleLocator(0.1))
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    ax.set_xlabel("sensibilite  (positifs reconnus)", fontsize=8.5, color=ENCRE_2)
    habiller(ax, "Sensibilite et specificite",
             "rond : vocabulaire d'origine   ·   triangle : vocabulaire renomme",
             "specificite  (negatifs rejetes)")
    ax.xaxis.grid(True, color=GRILLE, linewidth=0.7)
    enregistrer(fig, "fig3_sensibilite_specificite", table,
                ["modele", "lexique", "sensibilite", "specificite"])


def fig4_localisation(rangs):
    """Detecter n'est pas localiser."""
    pts = [r for r in rangs if r["lexique"] == "tous"]
    if not pts:
        return
    modeles = [r["modele"] for r in pts]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    largeur = 0.36
    table = []
    detect = [f(r["specificite"]) for r in pts]
    local = [f(r.get("localisation_moyenne")) for r in pts]
    xs = range(len(pts))
    for j, (vals, lab) in enumerate([(detect, "detecte le defaut"),
                                     (local, "nomme le bon element")]):
        pos = [i + (j - 0.5) * largeur for i in xs]
        tracables = [0.0 if v != v else v for v in vals]
        ax.bar(pos, tracables, largeur * 0.92, label=lab, color=SERIES[j],
               edgecolor=SURFACE, linewidth=1.4, zorder=3)
        for x, v in zip(pos, vals):
            # un modele qui n'a rien detecte n'a rien pu localiser : on ecrit
            # n/a plutot qu'un zero, qui se lirait comme un echec de nommage
            texte = "n/a" if v != v else f"{v:.2f}"
            ax.annotate(texte, (x, 0.0 if v != v else v), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=8,
                        color=ENCRE_2 if v != v else ENCRE)
    for r, d, l in zip(pts, detect, local):
        table.append([r["modele"], f"{d:.3f}", "n/a" if l != l else f"{l:.3f}",
                      r.get("n_localisation", "")])
    ax.set_xticks(list(xs)); ax.set_xticklabels([court(m) for m in modeles])
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    habiller(ax, "Detecter un defaut et savoir lequel",
             "sur les items ablates uniquement", "proportion")
    ax.legend(loc="upper right", fontsize=8.5)
    enregistrer(fig, "fig4_detection_localisation", table,
                ["modele", "taux_detection", "taux_localisation", "n_localisation"])


def _mcc(y, p):
    tp = sum(1 for a, b in zip(y, p) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y, p) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y, p) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y, p) if a == 1 and b == 0)
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return (tp * tn - fp * fn) / den if den else 0.0


def fig6_par_execution(reponses):
    """MCC de chaque execution k prise isolement : une trajectoire plate montre
    que le resultat ne depend pas de l'execution qu'on aurait gardee."""
    base = [r for r in reponses if (r.get("variante") or "base") == "base"
            and r["statut"] == "ok" and not r["modele_demande"].startswith("baseline/")]
    if not base:
        return
    modeles = sorted({r["modele_demande"] for r in base})
    ks = sorted({int(r["repetition"]) for r in base})
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    table = []
    for i, m in enumerate(modeles):
        ys = []
        for k in ks:
            sel = [r for r in base if r["modele_demande"] == m and int(r["repetition"]) == k
                   and r["lexique"] == "original"]
            v = _mcc([int(r["verite_terrain"]) for r in sel], [int(r["verdict"]) for r in sel])
            ys.append(v)
            table.append([m, k + 1, len(sel), f"{v:.3f}"])
        ax.plot([k + 1 for k in ks], ys, color=SERIES[i % 3], linewidth=2,
                marker="os^"[i % 3], markersize=8, markeredgecolor=SURFACE,
                markeredgewidth=1.6, label=court(m), zorder=3)
        ax.annotate(f"{ys[-1]:.2f}", (ks[-1] + 1, ys[-1]), textcoords="offset points",
                    xytext=(8, -3), fontsize=8, color=ENCRE)
    ax.set_xticks([k + 1 for k in ks])
    ax.set_xlim(0.7, len(ks) + 0.6)
    ax.set_ylim(min(-0.1, ax.get_ylim()[0]), 1.28)
    ax.axhline(0, color=NEUTRE, linewidth=1, linestyle=(0, (4, 3)), zorder=1)
    ax.set_xlabel("execution k", fontsize=8.5, color=ENCRE_2)
    habiller(ax, "Accord avec le gold standard, execution par execution",
             "vocabulaire d'origine, items naturels et ablates", "MCC")
    ax.legend(loc="upper center", fontsize=8.5, ncol=len(modeles), bbox_to_anchor=(0.5, 1.0))
    enregistrer(fig, "fig6_par_execution", table, ["modele", "execution", "n", "MCC"])


def fig7_calibration(reponses):
    """Accuracy selon la confiance declaree. Les niveaux verbaux sont places a
    0,25 / 0,60 / 0,90 par convention ; une confiance verbale n'est pas une
    probabilite et cette convention est affichee dans la figure."""
    base = [r for r in reponses if (r.get("variante") or "base") == "base"
            and r["statut"] == "ok" and r.get("confiance") in ("low", "medium", "high")
            and not r["modele_demande"].startswith("baseline/")]
    if not base:
        return
    niveaux = ["low", "medium", "high"]
    valeur = {"low": 0.25, "medium": 0.60, "high": 0.90}
    modeles = sorted({r["modele_demande"] for r in base})
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    largeur = 0.8 / max(1, len(modeles))
    table = []
    for i, m in enumerate(modeles):
        xs, ys, ns = [], [], []
        for j, nv in enumerate(niveaux):
            sel = [r for r in base if r["modele_demande"] == m and r["confiance"] == nv]
            if not sel:
                continue
            acc = sum(int(r["verdict"]) == int(r["verite_terrain"]) for r in sel) / len(sel)
            xs.append(j + (i - (len(modeles) - 1) / 2) * largeur)
            ys.append(acc); ns.append(len(sel))
            table.append([m, nv, len(sel), f"{acc:.3f}", valeur[nv]])
        ax.bar(xs, ys, largeur * 0.9, color=SERIES[i % 3], edgecolor=SURFACE,
               linewidth=1.4, label=court(m), zorder=3)
        for x, y, nn in zip(xs, ys, ns):
            ax.annotate(f"{y:.2f}\nn={nn}", (x, y), textcoords="offset points",
                        xytext=(0, 3), ha="center", fontsize=6.8, color=ENCRE)
    for j, nv in enumerate(niveaux):
        ax.plot([j - 0.45, j + 0.45], [valeur[nv]] * 2, color=ENCRE_2, linewidth=1.3,
                linestyle=(0, (4, 3)), zorder=4)
    ax.set_xticks(range(len(niveaux)))
    ax.set_xticklabels(["faible", "moyenne", "elevee"])
    ax.set_ylim(0, 1.2)
    ax.yaxis.set_major_locator(MultipleLocator(0.25))
    ax.set_xlabel("confiance declaree par le modele", fontsize=8.5, color=ENCRE_2)
    habiller(ax, "Calibration de la confiance declaree",
             "pointille : confiance supposee (0,25 / 0,60 / 0,90)  ·  "
             "barre sous le pointille : modele trop sur de lui", "accuracy du verdict")
    ax.legend(loc="upper left", fontsize=8, ncol=len(modeles), bbox_to_anchor=(0, 1.0))
    enregistrer(fig, "fig7_calibration", table,
                ["modele", "confiance", "n", "accuracy", "confiance_supposee"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metriques", default="metriques_exploitable.csv")
    ap.add_argument("--tests", default="tests.csv")
    ap.add_argument("--reponses", default="resultats_parses.csv",
                    help="reponses individuelles, pour les figures 6 et 7")
    a = ap.parse_args()

    rangs = list(csv.DictReader(open(a.metriques, encoding="utf-8")))
    if not rangs:
        raise SystemExit("fichier de metriques vide")
    print(f"{len(rangs)} lignes de metriques\n")
    fig1_mcc(rangs)
    fig2_conditions(rangs)
    fig3_sens_spec(rangs)
    fig4_localisation(rangs)
    if pathlib.Path(a.reponses).exists():
        reponses = list(csv.DictReader(open(a.reponses, encoding="utf-8")))
        fig6_par_execution(reponses)
        fig7_calibration(reponses)
    print(f"\nPDF vectoriels pour LaTeX, PNG 300 dpi, et la table de chaque figure "
          f"en CSV, dans {SORTIE}/")


if __name__ == "__main__":
    main()
