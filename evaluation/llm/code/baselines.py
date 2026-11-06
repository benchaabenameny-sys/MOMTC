#!/usr/bin/env python3
"""Les trois references non-LLM du Path 4.

Elles bornent la lecture des resultats. Sans elles, un MCC de 0,45 ne veut rien
dire : on ignore ce qu'obtient un systeme qui ne comprend rien.

  majoritaire  repond toujours la classe majoritaire du gold standard. Son
               accuracy est le plancher que tout evaluateur doit franchir, et
               son MCC vaut zero par construction. C'est la reference qui
               demasque le juge complaisant.
  aleatoire    verdicts tires a pile ou face, repetes R fois pour en donner la
               distribution plutot qu'un tirage unique.
  lexical      verdict par recouvrement de surface entre la question et le
               fragment, sans aucun raisonnement sur les axiomes. Il mesure la
               part de la performance d'un modele qui s'explique par la simple
               presence des bons mots.

Note de mise en oeuvre, a reporter dans le papier. Le protocole mentionnait un
encodeur de phrases. L'environnement d'execution n'a pas d'acces reseau vers un
depot de modeles, et aucun encodeur n'y est installe ; la similarite est donc
calculee en TF-IDF sur n-grammes de mots et de caracteres. Ce choix sert en
realite mieux l'intention : la reference doit capturer le recouvrement LEXICAL,
et un encodeur de phrases y melerait de la similarite semantique, ce qui en
ferait un concurrent du modele plutot qu'un plancher.

Le seuil est regle sur les seuls items ablates, comme le prevoit le protocole :
le regler sur l'ensemble reviendrait a laisser la reference apprendre la
reponse.

Sortie : baselines_parses.csv, au format de resultats_parses.csv, pour que
metrics.py les traite exactement comme les modeles.
"""
import csv, json, pathlib, random, re

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

ITEMS = pathlib.Path("campaign_items_full.jsonl")   # variantes de prompt exclues
SORTIE = pathlib.Path("baselines_parses.csv")
R_ALEATOIRE = 5
GRAINE = 303

CHAMPS = ["empreinte", "prompt_version", "modele_demande", "modele_servi",
          "item_id", "cq_id", "stratum", "couverture", "condition", "lexique",
          "verite_terrain", "element_manquant_reel", "repetition", "horodatage",
          "statut", "methode_extraction", "verdict", "confiance",
          "element_manquant_predit", "raisonnement", "localisation_correcte", "detail"]


def ligne(it, modele, rep, verdict):
    return {"empreinte": f"BASE-{modele}-{it['item_id']}-{rep}",
            "prompt_version": "baseline", "modele_demande": modele,
            "modele_servi": modele, "item_id": it["item_id"], "cq_id": it["cq_id"],
            "stratum": it["stratum"], "couverture": it["couverture"],
            "condition": it["condition"], "lexique": it["lexique"],
            "verite_terrain": it["verite_terrain"],
            "element_manquant_reel": it["element_manquant"], "repetition": rep,
            "horodatage": "", "statut": "ok", "methode_extraction": "baseline",
            "verdict": verdict, "confiance": "", "element_manquant_predit": "",
            "raisonnement": "", "localisation_correcte": "", "detail": ""}


def mots(texte):
    """Decoupe un texte en mots, identifiants compris.

    Sans cela la reference lexicale ne mesure rien : `Threat_Actor_Profiling`
    reste un seul jeton et ne rencontre jamais le mot « threat » de la
    question. Il faut donc casser les underscores et les frontieres de casse,
    sinon le recouvrement est nul partout et la reference n'est pas une
    reference mais un generateur de zeros.
    """
    t = re.sub(r"[_:&\-/<>#.]+", " ", texte)
    t = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", t)
    return [m.lower() for m in re.findall(r"[A-Za-z][A-Za-z0-9]*", t)]


def similarites(items):
    """Cosinus TF-IDF entre la question et le fragment, par item."""
    vect = TfidfVectorizer(analyzer=mots, lowercase=False,
                           sublinear_tf=True, min_df=1)
    corpus = [it["question"] for it in items] + [it["fragment"] for it in items]
    X = vect.fit_transform(corpus)
    n = len(items)
    Q, F = X[:n], X[n:]
    num = np.asarray(Q.multiply(F).sum(axis=1)).ravel()
    den = (np.sqrt(np.asarray(Q.multiply(Q).sum(axis=1)).ravel())
           * np.sqrt(np.asarray(F.multiply(F).sum(axis=1)).ravel()))
    return np.divide(num, den, out=np.zeros_like(num), where=den > 0)


def seuil_sur_ablations(sims, items):
    """Seuil maximisant l'accuracy sur les SEULS items ablates et leurs
    homologues naturels de meme CQ. Regler sur tout le jeu reviendrait a
    laisser la reference voir les reponses qu'elle doit predire."""
    cq_ablatees = {it["cq_id"] for it in items if it["couverture"] == "ablate"}
    idx = [i for i, it in enumerate(items) if it["cq_id"] in cq_ablatees]
    y = np.array([items[i]["verite_terrain"] for i in idx])
    s = sims[idx]
    candidats = np.unique(np.round(s, 4))
    meilleur, score = float(np.median(s)), -1.0
    for t in candidats:
        acc = float(((s >= t).astype(int) == y).mean())
        if acc > score:
            meilleur, score = float(t), acc
    return meilleur, score, len(idx)


def main():
    items = [i for i in (json.loads(l) for l in open(ITEMS, encoding="utf-8"))
             if i.get("variante", "base") == "base"]
    lignes = []

    # 1. classe majoritaire du gold standard
    majoritaire = 1 if sum(i["verite_terrain"] for i in items) * 2 > len(items) else 0
    for it in items:
        lignes.append(ligne(it, "baseline/majoritaire", 0, majoritaire))

    # 2. aleatoire, R tirages
    rng = random.Random(GRAINE)
    for rep in range(R_ALEATOIRE):
        for it in items:
            lignes.append(ligne(it, "baseline/aleatoire", rep, rng.randint(0, 1)))

    # 3. lexical
    sims = similarites(items)
    seuil, acc, n_regl = seuil_sur_ablations(sims, items)
    for it, s in zip(items, sims):
        lignes.append(ligne(it, "baseline/lexical", 0, int(s >= seuil)))

    with open(SORTIE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CHAMPS)
        w.writeheader(); w.writerows(lignes)

    print(f"{len(lignes)} verdicts de reference -> {SORTIE}")
    print(f"  majoritaire : repond toujours {majoritaire}")
    print(f"  aleatoire   : {R_ALEATOIRE} tirages, graine {GRAINE}")
    print(f"  lexical     : seuil {seuil:.4f} regle sur {n_regl} items "
          f"(accuracy de reglage {acc:.3f})")
    print(f"  similarite  : min {sims.min():.3f}  med {np.median(sims):.3f}  "
          f"max {sims.max():.3f}")


if __name__ == "__main__":
    main()
