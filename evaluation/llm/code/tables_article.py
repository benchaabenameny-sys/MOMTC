#!/usr/bin/env python3
"""Toutes les valeurs de la section d'evaluation, calculees en un seul endroit.

Analyse principale : vocabulaire d'origine, items de base (39 CQ naturelles +
12 ablations = 51 items), verdict majoritaire sur K = 3 par modele, puis vote
des trois modeles. Le renommage coherent (question + fragment) et le renommage
du seul fragment sont des controles (Table 5). Les items de sensibilite et de
revision sont traites a part.

Sortie : article/valeurs.json, lu par le generateur LaTeX et par le
verificateur.
"""
import csv, json, math, pathlib, statistics, sys
from collections import defaultdict, Counter

import numpy as np

ICI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))
import metrics as M

M.B_BOOTSTRAP = 10000          # protocole : 10 000 reechantillonnages BCa
B = 10000

ANA = pathlib.Path(str(pathlib.Path(__file__).resolve().parent.parent / "results" / "analysis"))
OUT = ICI / "article"
OUT.mkdir(exist_ok=True)

LLM = ["meta-llama/llama-3.3-70b-instruct", "qwen/qwen-2.5-72b-instruct",
       "deepseek/deepseek-chat"]
COURT = {"meta-llama/llama-3.3-70b-instruct": "M1", "qwen/qwen-2.5-72b-instruct": "M2",
         "deepseek/deepseek-chat": "M3", "ensemble": "Ens"}


def nan2none(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, (np.floating,)):
        return nan2none(float(x))
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def propre(o):
    if isinstance(o, dict):
        return {k: propre(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [propre(v) for v in o]
    return nan2none(o)


def main():
    lignes = M.charger([ANA / "resultats_parses.csv", ANA / "baselines_parses.csv"])
    cat = {r["cq_id"]: r for r in csv.DictReader(open(str(pathlib.Path(__file__).resolve().parent / "01_cqs.csv"), encoding="utf-8"))}
    for l in lignes:
        l["difficulte"] = cat[l["cq_id"]]["difficulty"]
    base = [l for l in lignes if (l.get("variante") or "base") == "base"]
    variantes = [l for l in lignes if (l.get("variante") or "base") != "base"]
    agr_all = M.ajouter_ensemble(M.grouper(base, "exploitable"), LLM)
    V = {}

    def sel(mod, lex, extra=lambda r: True):
        return [r for r in agr_all if r["modele"] == mod and r["lexique"] == lex and extra(r)]

    # ---------------- Table 2 : performance agregee (original, n = 51) -------
    t2 = {}
    for mod in LLM + ["ensemble", "baseline/majoritaire", "baseline/lexical"]:
        for lex in ("original", "renomme_q", "renomme"):
            s = sel(mod, lex)
            b = M.bloc_metriques(s, f"{mod}|{lex}")
            y = [r["verite"] for r in s]; p = [r["vote"] for r in s]
            tp, tn, fp, fn = M.confusion(y, p)
            prec = tp / (tp + fp) if tp + fp else float("nan")
            rec = tp / (tp + fn) if tp + fn else float("nan")
            b["F1_pos"] = 2 * prec * rec / (prec + rec) if prec + rec else float("nan")
            b["precision"] = prec
            b["AC1_ic95"] = M.bca(y, p, M.gwet_ac1, b=B)
            t2[f"{mod}|{lex}"] = b
    # baseline aleatoire : esperance sur les 5 tirages
    rnd = defaultdict(list)
    for l in base:
        if l["modele_demande"] == "baseline/aleatoire":
            rnd[(l["lexique"], l["repetition"])].append(l)
    for lex in ("original", "renomme_q", "renomme"):
        tirages = []
        for rep in range(5):
            g = sorted(rnd[(lex, rep)], key=lambda x: x["item_id"])
            y = [x["verite_terrain"] for x in g]; p = [x["verdict"] for x in g]
            tp, tn, fp, fn = M.confusion(y, p)
            prec = tp / (tp + fp) if tp + fp else float("nan"); rec = tp / (tp + fn)
            tirages.append({"TP": tp, "TN": tn, "FP": fp, "FN": fn,
                            "balanced_accuracy": M.balanced_accuracy(y, p),
                            "F1_pos": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                            "f1_macro": M.f1_macro(y, p), "MCC": M.mcc(y, p),
                            "kappa_cohen": M.cohen_kappa(y, p), "AC1_gwet": M.gwet_ac1(y, p),
                            "n": len(y)})
        moy = {k: statistics.mean(t[k] for t in tirages) for k in tirages[0]}
        moy["MCC_sd"] = statistics.stdev(t["MCC"] for t in tirages)
        moy["MCC_min"] = min(t["MCC"] for t in tirages); moy["MCC_max"] = max(t["MCC"] for t in tirages)
        t2[f"baseline/aleatoire|{lex}"] = moy
    V["table2"] = t2

    # SPARQL : verdicts sur les 39 CQ naturelles (le chemin s'applique a
    # l'ontologie, pas aux fragments ablates)
    sp = list(csv.DictReader(open(ICI / "sparql_verdicts.csv", encoding="utf-8")))
    cles = list(sp[0].keys())
    V["sparql"] = {"n": len(sp), "colonnes": cles,
                   "schema_1": sum(1 for r in sp if str(r.get("verdict_schema", "")).strip() == "1"),
                   "instance_1": sum(1 for r in sp if str(r.get("verdict_instance", "")).strip() == "1")}

    # ---------------- run par run (Figure 6, moyenne +- ET) -------------------
    runs = defaultdict(dict)
    for mod in LLM:
        for lex in ("original", "renomme_q"):
            mccs = []
            for k in range(3):
                g = sorted([l for l in base if l["modele_demande"] == mod and l["lexique"] == lex
                            and l["repetition"] == k and l["verdict"] is not None],
                           key=lambda x: x["item_id"])
                y = [x["verite_terrain"] for x in g]; p = [x["verdict"] for x in g]
                mccs.append({"k": k + 1, "n": len(g), "MCC": M.mcc(y, p),
                             "BAcc": M.balanced_accuracy(y, p), "f1_macro": M.f1_macro(y, p)})
            runs[mod][lex] = {"par_run": mccs,
                              "MCC_moy": statistics.mean(r["MCC"] for r in mccs),
                              "MCC_sd": statistics.stdev(r["MCC"] for r in mccs)}
    V["runs"] = runs

    # ---------------- Table 3 : comparaisons appariees (original) ------------
    def paires(m1, m2, filtre=lambda r: True):
        d1 = {r["item_id"]: r for r in sel(m1, "original", filtre)}
        d2 = {r["item_id"]: r for r in sel(m2, "original", filtre)}
        com = sorted(set(d1) & set(d2))
        b = sum(1 for c in com if d1[c]["vote"] == d1[c]["verite"] and d2[c]["vote"] != d2[c]["verite"])
        c_ = sum(1 for c in com if d1[c]["vote"] != d1[c]["verite"] and d2[c]["vote"] == d2[c]["verite"])
        pr = [(d1[c]["verite"], d1[c]["vote"], d2[c]["vote"]) for c in com]
        dm, (lo, hi) = M.delta_bca(pr, M.mcc, b=B)
        return {"n": len(com), "b": b, "c": c_, "p": M.mcnemar_exact(b, c_),
                "dMCC": dm, "dMCC_ic": [lo, hi]}
    m1, m2, m3 = LLM
    t3 = {"M1 vs M2": paires(m1, m2), "M1 vs M3": paires(m1, m3), "M2 vs M3": paires(m2, m3),
          "Ensemble vs M3": paires("ensemble", m3)}
    # ensemble contre SPARQL : 39 CQ naturelles, SPARQL juste partout
    nat = sel("ensemble", "original", lambda r: r["couverture"] == "naturel")
    c_sp = sum(1 for r in nat if r["vote"] != r["verite"])
    t3["Ensemble vs SPARQL"] = {"n": len(nat), "b": 0, "c": c_sp, "p": M.mcnemar_exact(0, c_sp),
                                "dMCC": None, "dMCC_ic": None}
    # contamination : original contre renomme_q, et renomme_q contre renomme
    cont = {}
    for mod in LLM + ["ensemble"]:
        for a, bb in (("original", "renomme_q"), ("original", "renomme"), ("renomme_q", "renomme")):
            o = {r["cq_id"] + r["condition"]: r for r in sel(mod, a)}
            z = {r["cq_id"] + r["condition"]: r for r in sel(mod, bb)}
            com = sorted(set(o) & set(z))
            b = sum(1 for c in com if o[c]["vote"] == o[c]["verite"] and z[c]["vote"] != z[c]["verite"])
            c_ = sum(1 for c in com if o[c]["vote"] != o[c]["verite"] and z[c]["vote"] == z[c]["verite"])
            pr = [(o[c]["verite"], o[c]["vote"], z[c]["vote"]) for c in com]
            dm, (lo, hi) = M.delta_bca(pr, M.mcc, b=B)
            cont[f"{mod}|{a} vs {bb}"] = {"n": len(com), "b": b, "c": c_,
                                          "p": M.mcnemar_exact(b, c_), "dMCC": dm, "dMCC_ic": [lo, hi]}
    # BH sur la famille : Table 3 + contamination (original vs renomme_q et
    # original vs renomme, par modele et ensemble)
    fam = [("t3", k) for k in t3] + [("cont", k) for k in cont if "renomme_q vs renomme" not in k]
    q = M.benjamini_hochberg([(t3 if f == "t3" else cont)[k]["p"] for f, k in fam])
    for (f, k), qq in zip(fam, q):
        (t3 if f == "t3" else cont)[k]["q_BH"] = qq
    V["table3"] = t3; V["contamination"] = cont; V["famille_BH"] = len(fam)

    # ---------------- Table 4 : strates (ensemble, original) -----------------
    t4 = {}
    strates = [("A", lambda r: r["stratum"] == "A"), ("B", lambda r: r["stratum"] == "B"),
               ("C", lambda r: r["stratum"] == "C"), ("D", lambda r: r["stratum"] == "D"),
               ("E", lambda r: r["stratum"] == "E"), ("F", lambda r: r["stratum"] == "F"),
               ("cross", lambda r: r["stratum"] == "cross"),
               ("simple", lambda r: r["difficulte"] == "simple"),
               ("complex", lambda r: r["difficulte"] != "simple"),
               ("overall", lambda r: True)]
    for nom, f in strates:
        s = sel("ensemble", "original", f)
        y = [r["verite"] for r in s]; p = [r["vote"] for r in s]
        tp, tn, fp, fn = M.confusion(y, p)
        t4[nom] = {"n_items": len(s), "n_cq": sum(1 for r in s if r["couverture"] == "naturel"),
                   "n_abl": sum(1 for r in s if r["couverture"] == "ablate"),
                   "TP": tp, "TN": tn, "FP": fp, "FN": fn,
                   "precision": tp / (tp + fp) if tp + fp else float("nan"),
                   "recall": tp / (tp + fn) if tp + fn else float("nan"),
                   "specificity": tn / (tn + fp) if tn + fp else float("nan"),
                   "f1_macro": M.f1_macro(y, p), "MCC": M.mcc(y, p)}
    V["table4"] = t4
    V["difficulte_comptes"] = Counter(cat[c]["difficulty"] for c in cat)

    # ---------------- Table 5 : controles negatifs et robustesse -------------
    t5 = {}
    for mod in LLM + ["ensemble", "baseline/lexical"]:
        for lex in ("original", "renomme_q", "renomme"):
            for cond in ("A1", "A2", "A3"):
                s = sel(mod, lex, lambda r, c=cond: r["condition"] == c)
                det = sum(1 for r in s if r["vote"] == 0)
                t5[f"{mod}|{lex}|{cond}"] = {"n": len(s), "det": det, "rate": det / len(s),
                                             "wilson": M.wilson(det, len(s))}
            s = sel(mod, lex, lambda r: r["couverture"] == "ablate")
            det = sum(1 for r in s if r["vote"] == 0)
            t5[f"{mod}|{lex}|all"] = {"n": len(s), "det": det, "rate": det / len(s),
                                      "wilson": M.wilson(det, len(s))}
    V["table5"] = t5
    # bascule sous variantes de prompt (vote majoritaire de la variante contre
    # vote majoritaire de l'item de reference)
    ref = {(r["modele"], r["item_id"]): r["vote"] for r in agr_all}
    var = defaultdict(list)
    for l in variantes:
        if l["modele_demande"] in LLM:
            var[(l["modele_demande"], l["variante"], l["item_reference"], l["item_id"])].append(l["verdict"])
    flips = defaultdict(lambda: [0, 0])
    flips_ens = defaultdict(dict)
    for (mod, v, iref, iid), vs in var.items():
        maj = M.vote_majoritaire(vs)
        r0 = ref.get((mod, iref))
        if maj is None or r0 is None:
            continue
        flips[(mod, v)][1] += 1
        flips[(mod, v)][0] += int(maj != r0)
        flips_ens[(v, iref)][mod] = (maj, r0)
    fl = {}
    for (mod, v), (k, n) in flips.items():
        fl[f"{mod}|{v}"] = {"k": k, "n": n, "rate": k / n, "wilson": M.wilson(k, n)}
    for v in ("paraphrase", "reordre"):
        k = n = 0
        for (vv, iref), d in flips_ens.items():
            if vv != v or len(d) < 3:
                continue
            ens_v = int(sum(x[0] for x in d.values()) > 1)
            ens_r = int(sum(x[1] for x in d.values()) > 1)
            n += 1; k += int(ens_v != ens_r)
        fl[f"ensemble|{v}"] = {"k": k, "n": n, "rate": k / n if n else float("nan"),
                               "wilson": M.wilson(k, n) if n else None}
    V["flips"] = fl

    # ---------------- auto-coherence, calibration ------------------------------
    sc = {}
    for mod in LLM:
        s = sel(mod, "original")
        sc[mod] = {"SC": sum(r["sc"] for r in s) / len(s),
                   "items_SC_lt1": sum(1 for r in s if r["sc"] < 1), "n": len(s)}
        s2 = sel(mod, "renomme_q")
        sc[mod]["SC_renomme_q"] = sum(r["sc"] for r in s2) / len(s2)
        sc[mod]["items_SC_lt1_renomme_q"] = sum(1 for r in s2 if r["sc"] < 1)
    V["self_consistency"] = sc
    cal = {}
    niveaux = {"low": 0.25, "medium": 0.6, "high": 0.9}
    for mod in LLM:
        runs_ = [l for l in base if l["modele_demande"] == mod and l["lexique"] == "original"
                 and l["verdict"] is not None and l["confiance"]]
        par = defaultdict(list)
        for l in runs_:
            par[l["confiance"]].append(int(l["verdict"] == l["verite_terrain"]))
        n = len(runs_)
        e = sum(len(v) / n * abs(sum(v) / len(v) - niveaux[c]) for c, v in par.items())
        err = [l for l in runs_ if l["verdict"] != l["verite_terrain"]]
        cal[mod] = {"n": n, "ECE": e,
                    "niveaux": {c: {"n": len(v), "acc": sum(v) / len(v)} for c, v in par.items()},
                    "erreurs": len(err),
                    "erreurs_par_niveau": dict(Counter(l["confiance"] for l in err))}
    V["calibration"] = cal

    # ---------------- localisation --------------------------------------------
    V["localisation"] = {mod: {"rate": t2[f"{mod}|original"]["localisation_moyenne"],
                               "n": t2[f"{mod}|original"]["n_localisation"],
                               "rate_q": t2[f"{mod}|renomme_q"]["localisation_moyenne"],
                               "n_q": t2[f"{mod}|renomme_q"]["n_localisation"]} for mod in LLM}

    # ---------------- accord multi-juges --------------------------------------
    for lex in ("original", "renomme_q"):
        par_item = defaultdict(list)
        for r in agr_all:
            if r["modele"] in LLM and r["lexique"] == lex:
                par_item[r["item_id"]].append(r["vote"])
        mat = [[v.count(0), v.count(1)] for v in par_item.values() if len(v) == 3]
        V[f"fleiss_{lex}"] = M.fleiss_kappa(mat)

    # ---------------- Table 7 : desaccords de l'ensemble (original) ----------
    codes = list(csv.DictReader(open(ANA / "desaccords_codes.csv", encoding="utf-8"))) \
        if (ANA / "desaccords_codes.csv").exists() else \
        list(csv.DictReader(open(str(pathlib.Path(__file__).resolve().parent.parent / "results" / "analysis" / "desaccords_codes.csv"), encoding="utf-8")))
    E = {"R1": "E1", "R2": "E2", "R3": "E2", "R4": "E2", "R5": "E2", "R6": "E2", "R7": "E4",
         "F1": "E3", "F2": "E3", "F3": "E3", "F4": "E3"}
    t7 = []
    for lex in ("original", "renomme_q"):
        for r in sel("ensemble", lex):
            if r["vote"] == r["verite"]:
                continue
            runs_v = [l["verdict"] for l in base if l["item_id"] == r["item_id"]
                      and l["modele_demande"] in LLM and l["verdict"] is not None]
            sc_e = sum(1 for v in runs_v if v == r["vote"]) / len(runs_v)
            cs = sorted({c["code"] for c in codes if c["cq_id"] == r["cq_id"]
                         and c["condition"] == r["condition"] and c["lexique"] == lex})
            t7.append({"cq": r["cq_id"], "condition": r["condition"], "lexique": lex,
                       "module": r["stratum"], "vH": r["verite"], "vL": r["vote"],
                       "SC": sc_e, "codes": cs, "type": sorted({E[c] for c in cs})})
    V["table7"] = sorted(t7, key=lambda x: (x["lexique"] != "original", x["vH"], int(x["cq"][2:])))
    # comptes au niveau modele
    V["desaccords_modeles"] = Counter((c["type_erreur"], c["code"]) for c in codes)
    V["desaccords_modeles"] = {f"{a}|{b}": n for (a, b), n in V["desaccords_modeles"].items()}

    # ---------------- Table 9 : cout ------------------------------------------
    t9 = {}
    for mod in LLM:
        g = [l for l in lignes if l["modele_demande"] == mod]
        t9[mod] = {"calls": len(g),
                   "tok_in": sum(int(float(l["jetons_entree"] or 0)) for l in g),
                   "tok_out": sum(int(float(l["jetons_sortie"] or 0)) for l in g),
                   "cost": sum(float(l["cout_usd"] or 0) for l in g),
                   "latency_s": sum(float(l["duree_s"] or 0) for l in g),
                   "parse_ok": sum(1 for l in g if l["statut"] == "ok"),
                   "routed_ok": sum(1 for l in g if str(l["hebergeur_conforme"]) == "True"),
                   "t_min": min(l["horodatage"] for l in g), "t_max": max(l["horodatage"] for l in g)}
    V["table9"] = t9
    rev = [json.loads(l) for l in open(ANA / "revision_cq1.jsonl", encoding="utf-8")]
    V["revision"] = {"calls": len(rev), "t_min": min(l["horodatage"] for l in rev),
                     "t_max": max(l["horodatage"] for l in rev),
                     "cost": sum(float(l.get("cout_usd") or 0) for l in rev)}

    json.dump(propre(V), open(OUT / "valeurs.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("ecrit", OUT / "valeurs.json")


if __name__ == "__main__":
    main()
