#!/usr/bin/env python3
"""Metriques, intervalles de confiance et tests de la campagne.

Choix statistiques, et pourquoi.

MCC comme metrique principale. L'accuracy est trompeuse quand les classes sont
desequilibrees : ici 39 positifs pour 12 negatifs, un modele qui repond 1
partout obtient 0,765 d'accuracy sans rien comprendre. Le MCC ne vaut 0 que
pour une reponse sans information, quelle que soit la prevalence (Chicco &
Jurman 2020). Balanced accuracy et F1-macro sont donnes a cote, pour la
comparabilite avec la litterature.

Agregation des K repetitions par vote majoritaire. La stabilite entre
repetitions est mesuree a part, comme resultat propre : un modele qui change
d'avis d'un appel a l'autre n'est pas utilisable comme juge, meme avec une
bonne moyenne.

Intervalles. Wilson pour les proportions, qui ne deborde pas de [0,1] et reste
valable sur de petits effectifs, contrairement a l'approximation normale.
Bootstrap BCa pour MCC et F1-macro, qui n'ont pas de forme analytique simple ;
le reechantillonnage porte sur les ITEMS et non sur les reponses, puisque les
K repetitions d'un meme item ne sont pas independantes.

Tests. McNemar exact pour les comparaisons appariees (meme items, deux
conditions ou deux modeles) : le test du chi2 d'independance serait invalide,
les echantillons n'etant pas independants. Correction de Benjamini-Hochberg
sur l'ensemble des tests, le taux de faux positifs augmentant avec leur nombre.

Les sorties hors format sont comptees deux fois : une fois ecartees (analyse
sur les reponses exploitables), une fois comptees comme erreurs (analyse
conservatrice). Les deux tableaux sont produits, car ne publier que le premier
avantagerait les modeles qui respectent mal la consigne.

Usage :
    python metrics.py                        sur resultats_parses.csv
    python metrics.py --fichier <csv>        sur un autre fichier
"""
import argparse, csv, itertools, json, math, pathlib
from collections import defaultdict

import numpy as np
from scipy.stats import binomtest, norm

B_BOOTSTRAP = 5000
GRAINE = 20261028


# --------------------------------------------------------------------------
# metriques elementaires
# --------------------------------------------------------------------------
def confusion(y_vrai, y_pred):
    tp = sum(1 for a, b in zip(y_vrai, y_pred) if a == 1 and b == 1)
    tn = sum(1 for a, b in zip(y_vrai, y_pred) if a == 0 and b == 0)
    fp = sum(1 for a, b in zip(y_vrai, y_pred) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y_vrai, y_pred) if a == 1 and b == 0)
    return tp, tn, fp, fn


def mcc(y_vrai, y_pred):
    tp, tn, fp, fn = confusion(y_vrai, y_pred)
    den = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    if den == 0:
        return 0.0          # reponse sans information : convention usuelle
    return (tp * tn - fp * fn) / den


def f1_macro(y_vrai, y_pred):
    out = []
    for c in (0, 1):
        tp = sum(1 for a, b in zip(y_vrai, y_pred) if a == c and b == c)
        fp = sum(1 for a, b in zip(y_vrai, y_pred) if a != c and b == c)
        fn = sum(1 for a, b in zip(y_vrai, y_pred) if a == c and b != c)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        out.append(2 * p * r / (p + r) if p + r else 0.0)
    return sum(out) / 2


def balanced_accuracy(y_vrai, y_pred):
    tp, tn, fp, fn = confusion(y_vrai, y_pred)
    sens = tp / (tp + fn) if tp + fn else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    return (sens + spec) / 2


def cohen_kappa(y_vrai, y_pred):
    n = len(y_vrai)
    if n == 0:
        return float("nan")
    po = sum(1 for a, b in zip(y_vrai, y_pred) if a == b) / n
    pe = sum((sum(1 for a in y_vrai if a == c) / n) * (sum(1 for b in y_pred if b == c) / n)
             for c in (0, 1))
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def pabak(y_vrai, y_pred):
    """Kappa ajuste sur la prevalence et le biais : 2*po - 1.

    Cohen's kappa s'effondre vers zero quand les marges sont tres desequilibrees,
    meme lorsque l'accord observe est eleve - le paradoxe du kappa (Feinstein &
    Cicchetti 1990 ; Byrt et al. 1993). PABAK est donne a cote pour que cette
    chute soit attribuee a la prevalence et non lue comme un desaccord.
    """
    if not y_vrai:
        return float("nan")
    po = sum(1 for a, b in zip(y_vrai, y_pred) if a == b) / len(y_vrai)
    return 2 * po - 1


def gwet_ac1(y_vrai, y_pred):
    """AC1 de Gwet : stable la ou kappa se degrade sous forte prevalence."""
    n = len(y_vrai)
    if n == 0:
        return float("nan")
    po = sum(1 for a, b in zip(y_vrai, y_pred) if a == b) / n
    pi = [(sum(1 for a in y_vrai if a == c) + sum(1 for b in y_pred if b == c)) / (2 * n)
          for c in (0, 1)]
    pe = 2 * pi[0] * pi[1]
    return (po - pe) / (1 - pe) if pe != 1 else float("nan")


def fleiss_kappa(matrice):
    """Accord entre plus de deux juges.

    `matrice` : une ligne par item, deux colonnes (nombre de votes 0, de votes 1).
    L'accord entre les |M| modeles est une quantite multi-juges ; l'estimer par
    des kappas de Cohen pris deux a deux donnerait une autre grandeur.
    """
    m = [r for r in matrice if sum(r) > 1]
    if not m:
        return float("nan")
    n_juges = sum(m[0])
    if any(sum(r) != n_juges for r in m):
        return float("nan")      # plan desequilibre : Fleiss ne s'applique pas
    N = len(m)
    p_cat = [sum(r[c] for r in m) / (N * n_juges) for c in (0, 1)]
    P = [(sum(x * x for x in r) - n_juges) / (n_juges * (n_juges - 1)) for r in m]
    p_barre = sum(P) / N
    pe = sum(p * p for p in p_cat)
    return (p_barre - pe) / (1 - pe) if pe != 1 else float("nan")


def ece(paires, n_classes=3):
    """Erreur de calibration attendue, sur les niveaux de confiance declares.

    `paires` : liste de (niveau, correct). Les niveaux verbaux sont places sur
    [0,1] a des valeurs conventionnelles, indiquees dans le papier : une
    confiance verbale n'est pas une probabilite, et la convention doit etre
    affichee plutot que supposee.
    """
    valeur = {"low": 0.25, "medium": 0.60, "high": 0.90}
    groupes = {}
    for niveau, correct in paires:
        if niveau in valeur:
            groupes.setdefault(niveau, []).append(correct)
    n = sum(len(v) for v in groupes.values())
    if n == 0:
        return float("nan"), {}
    detail, total = {}, 0.0
    for niveau, v in groupes.items():
        acc = sum(v) / len(v)
        detail[niveau] = {"n": len(v), "accuracy": acc, "confiance": valeur[niveau]}
        total += len(v) / n * abs(acc - valeur[niveau])
    return total, detail


def wilson(k, n, alpha=0.05):
    """Intervalle de Wilson pour une proportion."""
    if n == 0:
        return (float("nan"), float("nan"))
    z = norm.ppf(1 - alpha / 2)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def bca(y_vrai, y_pred, fonction, b=B_BOOTSTRAP, alpha=0.05, graine=GRAINE):
    """Intervalle bootstrap BCa, reechantillonnage sur les items."""
    n = len(y_vrai)
    if n < 5:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(graine)
    theta = fonction(y_vrai, y_pred)
    idx = np.arange(n)

    reps = np.empty(b)
    for i in range(b):
        s = rng.choice(idx, size=n, replace=True)
        reps[i] = fonction([y_vrai[j] for j in s], [y_pred[j] for j in s])

    prop = np.mean(reps < theta)
    if prop <= 0 or prop >= 1:        # distribution degeneree
        return (float(np.percentile(reps, 100 * alpha / 2)),
                float(np.percentile(reps, 100 * (1 - alpha / 2))))
    z0 = norm.ppf(prop)

    jack = np.empty(n)
    for i in range(n):
        g = [j for j in idx if j != i]
        jack[i] = fonction([y_vrai[j] for j in g], [y_pred[j] for j in g])
    m = jack.mean()
    num = ((m - jack) ** 3).sum()
    den = 6 * (((m - jack) ** 2).sum() ** 1.5)
    a = num / den if den else 0.0

    def borne(q):
        zq = norm.ppf(q)
        ajuste = z0 + (z0 + zq) / (1 - a * (z0 + zq))
        return float(np.percentile(reps, 100 * norm.cdf(ajuste)))

    return (borne(alpha / 2), borne(1 - alpha / 2))


def delta_bca(paires, fonction, b=B_BOOTSTRAP, alpha=0.05, graine=GRAINE):
    """Ecart d'une metrique entre deux conditions appariees, et son IC BCa.

    `paires` : liste de (verite, pred_condition_1, pred_condition_2).
    Le reechantillonnage porte sur les items, en conservant l'appariement : les
    deux conditions portent sur les memes items, les traiter comme independants
    sous-estimerait la precision de l'ecart.

    C'est cette quantite qu'il faut rapporter, et non la seule valeur p : avec
    une cinquantaine d'items apparies, McNemar ne detecte que les effets
    importants, et un ecart reel peut rester non significatif. La taille
    d'effet et son intervalle disent ce que le test ne dit pas.
    """
    if len(paires) < 5:
        return float("nan"), (float("nan"), float("nan"))
    y = [p[0] for p in paires]
    a1 = [p[1] for p in paires]
    a2 = [p[2] for p in paires]
    theta = fonction(y, a1) - fonction(y, a2)

    rng = np.random.default_rng(graine)
    n = len(paires)
    idx = np.arange(n)
    reps = np.empty(b)
    for i in range(b):
        s = rng.choice(idx, size=n, replace=True)
        reps[i] = (fonction([y[j] for j in s], [a1[j] for j in s])
                   - fonction([y[j] for j in s], [a2[j] for j in s]))

    prop = np.mean(reps < theta)
    if prop <= 0 or prop >= 1:
        return theta, (float(np.percentile(reps, 100 * alpha / 2)),
                       float(np.percentile(reps, 100 * (1 - alpha / 2))))
    z0 = norm.ppf(prop)
    jack = np.empty(n)
    for i in range(n):
        g = [j for j in idx if j != i]
        jack[i] = (fonction([y[j] for j in g], [a1[j] for j in g])
                   - fonction([y[j] for j in g], [a2[j] for j in g]))
    m = jack.mean()
    den = 6 * (((m - jack) ** 2).sum() ** 1.5)
    acc = ((m - jack) ** 3).sum() / den if den else 0.0

    def borne(q):
        zq = norm.ppf(q)
        return float(np.percentile(reps, 100 * norm.cdf(z0 + (z0 + zq) / (1 - acc * (z0 + zq)))))

    return theta, (borne(alpha / 2), borne(1 - alpha / 2))


def mcnemar_exact(b, c):
    """Test exact de McNemar sur les paires discordantes."""
    if b + c == 0:
        return 1.0
    return float(binomtest(b, b + c, 0.5).pvalue)


def benjamini_hochberg(pvals, q=0.05):
    """Renvoie les seuils ajustes (q-values) dans l'ordre d'entree."""
    m = len(pvals)
    ordre = sorted(range(m), key=lambda i: pvals[i])
    ajuste = [0.0] * m
    precedent = 1.0
    for rang, i in enumerate(reversed(ordre), 1):
        k = m - rang + 1
        val = min(precedent, pvals[i] * m / k)
        ajuste[i] = val
        precedent = val
    return ajuste


# --------------------------------------------------------------------------
# agregation
# --------------------------------------------------------------------------
def vote_majoritaire(verdicts):
    """Vote sur les K repetitions. Egalite -> None (indecis)."""
    v = [x for x in verdicts if x in (0, 1)]
    if not v:
        return None
    u, z = v.count(1), v.count(0)
    if u == z:
        return None
    return 1 if u > z else 0


def charger(fichiers):
    lignes = []
    for fichier in fichiers:
        lignes += list(csv.DictReader(open(fichier, encoding="utf-8")))
    for l in lignes:
        l["verite_terrain"] = int(l["verite_terrain"])
        l["verdict"] = int(l["verdict"]) if l["verdict"] not in ("", None) else None
        l["repetition"] = int(l["repetition"])
        l["localisation_correcte"] = (int(l["localisation_correcte"])
                                      if l["localisation_correcte"] not in ("", None) else None)
    return lignes


def grouper(lignes, mode):
    """(modele, lexique, item) -> dict agrege.

    mode 'exploitable' : les sorties hors format sont ignorees.
    mode 'conservateur': elles comptent comme une reponse fausse.
    """
    par = defaultdict(list)
    for l in lignes:
        par[(l["modele_demande"], l["lexique"], l["item_id"])].append(l)

    out = []
    for (mod, lex, item), g in par.items():
        verdicts = [x["verdict"] for x in g]
        if mode == "conservateur":
            verdicts = [v if v is not None else 1 - g[0]["verite_terrain"]
                        for v in verdicts]
        vote = vote_majoritaire(verdicts)
        if vote is None:
            if mode == "conservateur":
                vote = 1 - g[0]["verite_terrain"]
            else:
                continue
        exploitables = [x for x in g if x["statut"] == "ok"]
        loc = [x["localisation_correcte"] for x in exploitables
               if x["localisation_correcte"] is not None]
        # auto-coherence : part de la modalite dominante parmi les K reponses
        v_def = [v for v in verdicts if v is not None]
        sc = (max(v_def.count(0), v_def.count(1)) / len(v_def)) if v_def else float("nan")
        conf = [(x["confiance"], int(x["verdict"] == x["verite_terrain"]))
                for x in exploitables if x["confiance"] and x["verdict"] is not None]
        out.append({
            "modele": mod, "lexique": lex, "item_id": item,
            "cq_id": g[0]["cq_id"], "stratum": g[0]["stratum"],
            "couverture": g[0]["couverture"], "condition": g[0]["condition"],
            "difficulte": g[0].get("difficulte", ""),
            "verite": g[0]["verite_terrain"], "vote": vote,
            "k": len(g), "k_ok": len(exploitables), "sc": sc,
            "unanime": int(len(set(v for v in verdicts if v is not None)) == 1),
            "localisation": (sum(loc) / len(loc)) if loc else None,
            "confiances": conf,
        })
    return out


def ajouter_ensemble(agr, modeles_llm):
    """Verdict d'ensemble : majorite des votes-modele, sur les seuls LLM.

    Les references non-LLM n'y participent pas : les inclure ferait voter le
    plancher avec les candidats qu'il sert a jauger.
    """
    par_item = {}
    for r in agr:
        if r["modele"] in modeles_llm:
            par_item.setdefault(r["item_id"], []).append(r)
    ajout = []
    for item, g in par_item.items():
        votes = [r["vote"] for r in g]
        if len(votes) < 2:
            continue
        maj = 1 if votes.count(1) > votes.count(0) else 0
        base = dict(g[0])
        base.update({"modele": "ensemble", "vote": maj,
                     "sc": max(votes.count(0), votes.count(1)) / len(votes),
                     "unanime": int(len(set(votes)) == 1),
                     "localisation": None, "confiances": []})
        ajout.append(base)
    return agr + ajout


def bloc_metriques(sous_ensemble, etiquette):
    y = [r["verite"] for r in sous_ensemble]
    p = [r["vote"] for r in sous_ensemble]
    if not y:
        return None
    tp, tn, fp, fn = confusion(y, p)
    acc = (tp + tn) / len(y)
    sens = tp / (tp + fn) if tp + fn else float("nan")
    spec = tn / (tn + fp) if tn + fp else float("nan")
    m, f = mcc(y, p), f1_macro(y, p)
    m_lo, m_hi = bca(y, p, mcc)
    f_lo, f_hi = bca(y, p, f1_macro)
    a_lo, a_hi = wilson(tp + tn, len(y))
    k_lo, k_hi = bca(y, p, cohen_kappa)
    # La localisation ne se mesure que sur les items ablates que le modele a
    # EFFECTIVEMENT rejetes. La conditionner au vote majoritaire, comme la
    # detection, evite l'incoherence d'un modele qui ne detecte rien mais
    # afficherait un taux de localisation non nul grace a quelques repetitions
    # isolees. La question posee est : parmi les defauts qu'il a vus, combien
    # a-t-il su nommer ?
    loc = [r["localisation"] for r in sous_ensemble
           if r["couverture"] == "ablate" and r["vote"] == 0
           and r["localisation"] is not None]
    return {
        "groupe": etiquette, "n": len(y), "TP": tp, "TN": tn, "FP": fp, "FN": fn,
        "accuracy": acc, "acc_ic95_bas": a_lo, "acc_ic95_haut": a_hi,
        "sensibilite": sens, "specificite": spec,
        "balanced_accuracy": balanced_accuracy(y, p),
        "f1_macro": f, "f1_ic95_bas": f_lo, "f1_ic95_haut": f_hi,
        "MCC": m, "mcc_ic95_bas": m_lo, "mcc_ic95_haut": m_hi,
        "kappa_cohen": cohen_kappa(y, p), "kappa_ic95_bas": k_lo,
        "kappa_ic95_haut": k_hi, "PABAK": pabak(y, p), "AC1_gwet": gwet_ac1(y, p),
        "auto_coherence_SC": sum(r["sc"] for r in sous_ensemble) / len(sous_ensemble),
        "items_SC_inferieur_1": sum(1 for r in sous_ensemble if r["sc"] < 1),
        "unanimite_K": sum(r["unanime"] for r in sous_ensemble) / len(sous_ensemble),
        "localisation_moyenne": (sum(loc) / len(loc)) if loc else float("nan"),
        "n_localisation": len(loc),
    }


def complementaires(toutes, variantes, modeles_llm, prefixe):
    """Section 4.8 (sensibilite au prompt), Table 9 (cout) et conformite du routage."""
    out = []

    # --- routage : chaque reponse doit venir de l'hebergeur epingle ---------
    llm = [l for l in toutes if l["modele_demande"] in modeles_llm and l["statut"] != "erreur_appel"]
    if llm and "hebergeur_conforme" in llm[0]:
        hors = [l for l in llm if str(l.get("hebergeur_conforme")) not in ("True", "true", "1", "")]
        out.append(("routage", "reponses hors hebergeur epingle", len(hors), len(llm)))
        print(f"Routage : {len(llm) - len(hors)}/{len(llm)} reponses servies par l'hebergeur epingle")

    # --- sensibilite : le verdict change-t-il avec la formulation ? --------
    def vote(rows):
        v = [int(r["verdict"]) for r in rows if str(r.get("verdict")) in ("0", "1")]
        if not v or v.count(0) == v.count(1):
            return None
        return int(v.count(1) > v.count(0))

    base_par = defaultdict(list)
    for l in toutes:
        if (l.get("variante") or "base") == "base":
            base_par[(l["modele_demande"], l["item_id"])].append(l)
    var_par = defaultdict(list)
    for l in variantes:
        var_par[(l["modele_demande"], l["variante"], l["item_reference"], l["item_id"])].append(l)

    print("\nSensibilite au prompt (section 4.8) : part des items dont le verdict majoritaire change")
    for m in modeles_llm:
        for typ in ("paraphrase", "reordre"):
            paires = []
            for (mm, t, ref, iid), rows in var_par.items():
                if mm != m or t != typ:
                    continue
                vb, vv = vote(base_par.get((m, ref), [])), vote(rows)
                if vb is not None and vv is not None:
                    paires.append(int(vb != vv))
            if paires:
                k, nn = sum(paires), len(paires)
                lo, hi = wilson(k, nn)
                print(f"   {m.split('/')[1][:28]:28} {typ:10} bascule {k}/{nn} = {k/nn:.2f}  "
                      f"IC95 [{lo:.2f}, {hi:.2f}]")
                out.append(("sensibilite", f"{m} | {typ}", k, nn))

    # --- Table 9 : appels, jetons, cout, duree ------------------------------
    print("\nCout et duree (Table 9)")
    def f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return 0.0
    for m in modeles_llm:
        rows = [l for l in toutes if l["modele_demande"] == m and l["statut"] != "erreur_appel"]
        if not rows:
            continue
        je = sum(f(r.get("jetons_entree")) for r in rows)
        js = sum(f(r.get("jetons_sortie")) for r in rows)
        cout = sum(f(r.get("cout_usd")) for r in rows)
        duree = sum(f(r.get("duree_s")) for r in rows)
        print(f"   {m.split('/')[1][:28]:28} appels {len(rows):5d}  jetons {int(je):>9,} / {int(js):>7,}"
              f"  cout {cout:7.4f} $  latence cumulee {duree / 60:6.1f} min")
        out.append(("cout", m, len(rows), f"{int(je)}|{int(js)}|{cout:.4f}|{duree:.0f}"))

    p = pathlib.Path(f"{prefixe}analyses_complementaires.csv")
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["analyse", "groupe", "k_ou_appels", "n_ou_detail"])
        w.writerows(out)
    print(f"ecrit : {p}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fichier", action="append",
                    help="repetable : resultats des modeles, puis des references")
    ap.add_argument("--cqs", default=str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv"))
    ap.add_argument("--prefixe", default="")
    a = ap.parse_args()

    lignes = charger(a.fichier or ["resultats_parses.csv"])

    # la difficulte vient du catalogue de CQ, pas des resultats
    diff = {r["cq_id"]: r.get("difficulty", "") for r in
            csv.DictReader(open(a.cqs, encoding="utf-8"))}
    for l in lignes:
        l["difficulte"] = diff.get(l["cq_id"], "")

    # Les items de la condition de sensibilite (section 4.8) sont des doublons
    # reformules d'items de base : les garder dans l'analyse principale
    # compterait deux fois les memes CQ. Ils sont analyses a part.
    variantes = [l for l in lignes if (l.get("variante") or "base") != "base"]
    lignes = [l for l in lignes if (l.get("variante") or "base") == "base"]

    n = len(lignes)
    conformes = sum(1 for l in lignes if l["statut"] == "ok")
    print(f"{n} reponses de base  |  exploitables {conformes} ({conformes/n:.1%})"
          f"  |  {len(variantes)} reponses de sensibilite, analysees a part\n")

    modeles_llm = sorted({l["modele_demande"] for l in lignes
                          if not l["modele_demande"].startswith("baseline/")})

    complementaires(lignes + variantes, variantes, modeles_llm, a.prefixe)

    tables, tests, extras = {}, [], {}
    for mode in ("exploitable", "conservateur"):
        agr = ajouter_ensemble(grouper(lignes, mode), modeles_llm)
        rangs = []
        for mod in sorted({r["modele"] for r in agr}):
            for lex in ("original", "renomme", "renomme_q", "tous"):
                # « tous » regroupe le vocabulaire d'origine et le renommage
                # coherent (question et fragment) quand il existe ; le renommage
                # du seul fragment, qui casse le pont lexical question-schema,
                # reste rapporte a part comme test de robustesse.
                pool = ({"original", "renomme_q"} if any(r["lexique"] == "renomme_q" for r in agr)
                        else {"original", "renomme"})
                sel = [r for r in agr if r["modele"] == mod
                       and (r["lexique"] == lex or (lex == "tous" and r["lexique"] in pool))]
                b = bloc_metriques(sel, f"{mod} | {lex}")
                if b:
                    rangs.append({**b, "modele": mod, "lexique": lex, "mode": mode})
            # par condition d'ablation : les quasi-correspondances sont-elles
            # plus difficiles que les suppressions ?
            for cond in ("A1", "A2", "A3"):
                sel = [r for r in agr if r["modele"] == mod and r["condition"] == cond]
                if sel:
                    det = sum(1 for r in sel if r["vote"] == 0)
                    lo, hi = wilson(det, len(sel))
                    rangs.append({"groupe": f"{mod} | {cond}", "modele": mod,
                                  "lexique": cond, "mode": mode, "n": len(sel),
                                  "accuracy": det / len(sel), "acc_ic95_bas": lo,
                                  "acc_ic95_haut": hi})
            # strates du papier : par module, et par difficulte
            for cle, valeurs in (("stratum", sorted({r["stratum"] for r in agr})),
                                 ("difficulte", sorted({r["difficulte"] for r in agr
                                                        if r["difficulte"]}))):
                for v in valeurs:
                    sel = [r for r in agr if r["modele"] == mod and r[cle] == v]
                    b = bloc_metriques(sel, f"{mod} | {v}")
                    if b:
                        rangs.append({**b, "modele": mod, "lexique": v, "mode": mode})
        tables[mode] = rangs

        if mode != "exploitable":
            continue

        # accord multi-juges entre les modeles evalues
        par_item = {}
        for r in agr:
            if r["modele"] in modeles_llm:
                par_item.setdefault(r["item_id"], []).append(r["vote"])
        matrice = [[v.count(0), v.count(1)] for v in par_item.values()
                   if len(v) == len(modeles_llm)]
        extras["fleiss_kappa_entre_modeles"] = fleiss_kappa(matrice)
        extras["n_items_fleiss"] = len(matrice)

        # calibration de la confiance declaree
        for mod in modeles_llm:
            paires = [c for r in agr if r["modele"] == mod for c in r["confiances"]]
            e, detail = ece(paires)
            extras[f"ECE::{mod}"] = e
            for niveau, d in detail.items():
                extras[f"calibration::{mod}::{niveau}"] = (
                    f"n={d['n']} accuracy={d['accuracy']:.3f} "
                    f"confiance_supposee={d['confiance']}")

        # comparaisons de vocabulaire, appariees par CQ et condition
        for lx1, lx2 in (("original", "renomme"), ("original", "renomme_q"),
                         ("renomme_q", "renomme")):
          for mod in sorted({r["modele"] for r in agr}):
            o = {r["cq_id"] + r["condition"]: r for r in agr
                 if r["modele"] == mod and r["lexique"] == lx1}
            z = {r["cq_id"] + r["condition"]: r for r in agr
                 if r["modele"] == mod and r["lexique"] == lx2}
            communs = sorted(set(o) & set(z))
            if not communs:
                continue
            b = sum(1 for c in communs
                    if o[c]["vote"] == o[c]["verite"] and z[c]["vote"] != z[c]["verite"])
            c_ = sum(1 for c in communs
                     if o[c]["vote"] != o[c]["verite"] and z[c]["vote"] == z[c]["verite"])
            paires = [(o[c]["verite"], o[c]["vote"], z[c]["vote"]) for c in communs]
            d_mcc, (d_lo, d_hi) = delta_bca(paires, mcc)
            tests.append({"famille": "contamination", "comparaison": f"{mod} : {lx1} vs {lx2}",
                          "n_paires": len(communs), "b": b, "c": c_,
                          "p": mcnemar_exact(b, c_),
                          "delta_MCC": d_mcc, "delta_ic95_bas": d_lo, "delta_ic95_haut": d_hi})

        # modeles deux a deux, sur les items communs
        mods = sorted({r["modele"] for r in agr})
        for m1, m2 in itertools.combinations(mods, 2):
            d1 = {r["item_id"]: r for r in agr if r["modele"] == m1}
            d2 = {r["item_id"]: r for r in agr if r["modele"] == m2}
            communs = sorted(set(d1) & set(d2))
            b = sum(1 for c in communs
                    if d1[c]["vote"] == d1[c]["verite"] and d2[c]["vote"] != d2[c]["verite"])
            c_ = sum(1 for c in communs
                     if d1[c]["vote"] != d1[c]["verite"] and d2[c]["vote"] == d2[c]["verite"])
            paires = [(d1[c]["verite"], d1[c]["vote"], d2[c]["vote"]) for c in communs]
            d_mcc, (d_lo, d_hi) = delta_bca(paires, mcc)
            tests.append({"famille": "modeles", "comparaison": f"{m1} vs {m2}",
                          "n_paires": len(communs), "b": b, "c": c_,
                          "p": mcnemar_exact(b, c_),
                          "delta_MCC": d_mcc, "delta_ic95_bas": d_lo, "delta_ic95_haut": d_hi})

    if tests:
        q = benjamini_hochberg([t["p"] for t in tests])
        for t, v in zip(tests, q):
            t["q_BH"] = v

    pref = a.prefixe
    for mode, rangs in tables.items():
        p = pathlib.Path(f"{pref}metriques_{mode}.csv")
        champs = sorted({k for r in rangs for k in r})
        tete = ["groupe", "modele", "lexique", "mode", "n", "TP", "TN", "FP", "FN",
                "accuracy", "acc_ic95_bas", "acc_ic95_haut", "sensibilite",
                "specificite", "balanced_accuracy", "f1_macro", "f1_ic95_bas",
                "f1_ic95_haut", "MCC", "mcc_ic95_bas", "mcc_ic95_haut",
                "kappa_cohen", "kappa_ic95_bas", "kappa_ic95_haut", "PABAK",
                "AC1_gwet", "auto_coherence_SC", "items_SC_inferieur_1",
                "unanimite_K", "localisation_moyenne", "n_localisation"]
        ordre = [c for c in tete if c in champs] + [c for c in champs if c not in tete]
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=ordre); w.writeheader(); w.writerows(rangs)
        print(f"ecrit : {p}")

    if tests:
        p = pathlib.Path(f"{pref}tests.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(tests[0].keys()))
            w.writeheader(); w.writerows(tests)
        print(f"ecrit : {p}")

    if extras:
        p = pathlib.Path(f"{pref}mesures_complementaires.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["mesure", "valeur"])
            for k, v in extras.items():
                w.writerow([k, f"{v:.4f}" if isinstance(v, float) else v])
        print(f"ecrit : {p}")

    print("\n--- analyse principale (sorties hors format ecartees) ---")
    print(f"{'modele':28} {'lex':9} {'n':>4} {'acc':>6} {'bal':>6} {'F1m':>6} "
          f"{'MCC':>6} {'IC95 MCC':>16} {'unanim':>7} {'local':>6}")
    for r in tables["exploitable"]:
        if r.get("lexique") in ("original", "renomme", "renomme_q", "tous") and "MCC" in r:
            loc = r["localisation_moyenne"]
            print(f"{r['modele'][:28]:28} {r['lexique']:9} {r['n']:4d} "
                  f"{r['accuracy']:6.3f} {r['balanced_accuracy']:6.3f} "
                  f"{r['f1_macro']:6.3f} {r['MCC']:6.3f} "
                  f"[{r['mcc_ic95_bas']:5.2f}, {r['mcc_ic95_haut']:5.2f}]".ljust(17)
                  + f"{r['unanimite_K']:7.2f} "
                  + ("  n/a" if loc != loc else f"{loc:6.3f}"))

    if tests:
        print("\n--- comparaisons appariees ---")
        print("dMCC : ecart de MCC et son IC95 bootstrap BCa, sur tous les items.")
        print("p    : McNemar exact, qui porte sur l'ACCURACY et n'utilise que les")
        print("       paires discordantes (b et c). Les deux quantites ne mesurent pas")
        print("       la meme chose et peuvent diverger : un ecart de MCC dont l'IC")
        print("       exclut zero peut s'accompagner d'un McNemar non significatif")
        print("       quand les paires discordantes sont peu nombreuses.")
        print()
        print(f"{'':2}{'comparaison':48} {'dMCC':>7} {'IC95 (MCC)':>18} "
              f"{'b':>3} {'c':>3} {'p (acc)':>8} {'q_BH':>7}")
        for t in tests:
            sig = "*" if t["q_BH"] < 0.05 else " "
            ic = f"[{t['delta_ic95_bas']:+.2f}, {t['delta_ic95_haut']:+.2f}]"
            print(f"{sig} {t['comparaison'][:48]:48} {t['delta_MCC']:+7.3f} {ic:>18} "
                  f"{t['b']:3d} {t['c']:3d} {t['p']:8.4f} {t['q_BH']:7.4f}")
        print("\nRapporter l'ecart et son intervalle avant la valeur p : avec une")
        print("cinquantaine d'items apparies, seul un effet important atteint la")
        print("significativite, et un resultat non significatif n'est pas un resultat nul.")


if __name__ == "__main__":
    main()
