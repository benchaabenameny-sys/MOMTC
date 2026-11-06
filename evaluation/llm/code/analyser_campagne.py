#!/usr/bin/env python3
"""Enchaine toute l'analyse a partir du fichier de resultats de la campagne.

    python analyser_campagne.py resultats_campagne.jsonl [erreurs_campagne.jsonl]

Etapes : controle d'integrite, analyse syntaxique, references non-LLM,
metriques et tests, figures. Tout est ecrit dans un dossier analyse/ a cote
du fichier de resultats, sans rien ecraser ailleurs.
"""
import json, pathlib, re, subprocess, sys, collections, shutil

ICI = pathlib.Path(__file__).resolve().parent


def lancer(*cmd, cwd):
    print(f"\n$ {' '.join(map(str, cmd))}")
    r = subprocess.run([sys.executable, *map(str, cmd)], cwd=cwd)
    if r.returncode:
        sys.exit(f"echec de l'etape : {cmd[0]}")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    res = pathlib.Path(sys.argv[1]).resolve()
    err = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    out = res.parent / "analyse"
    out.mkdir(exist_ok=True)

    # --- integrite ----------------------------------------------------------
    lignes = [json.loads(l) for l in open(res, encoding="utf-8")]
    emp = collections.Counter(l["empreinte"] for l in lignes)
    items = [json.loads(l) for l in open(ICI / "campaign_items_full.jsonl", encoding="utf-8")]
    sha = {i["item_id"]: i["sha256_12"] for i in items}
    print(f"{len(lignes)} lignes, {len(emp)} empreintes uniques, "
          f"{sum(1 for c in emp.values() if c > 1)} doublons")
    hors = [l for l in lignes if l.get("item_sha256_12") and sha.get(l["item_id"]) != l["item_sha256_12"]]
    print(f"items dont le contenu differe de la version de reference : {len(hors)}")
    if hors:
        sys.exit("ARRET : des reponses portent sur une autre version des items.")
    texte = res.read_text(encoding="utf-8")
    if "sk-or-" in texte:
        sys.exit("ARRET : une trace de cle d'API figure dans le fichier.")
    par_modele = collections.Counter(l["modele_demande"] for l in lignes)
    print("reponses par modele :", dict(par_modele))
    # Mistral Large a ete retire du jury (limitation de debit chez son seul
    # hebergeur) : ses quelques reponses restent dans le fichier brut mais
    # sont ecartees de l'analyse, et leur nombre est consigne.
    exclus = {"mistralai/mistral-large-2512"}
    # Reverification apres la revision de CQ1 (Table 8) : analysee a part, elle
    # porte sur l'ontologie revisee (v2.0.0) et non sur le fichier evalue.
    # "revision_v11" est l'etiquette interne de cette variante dans le journal brut.
    revision = [l for l in lignes if l.get("variante") == "revision_v11"
                and l["modele_demande"] not in exclus]
    if revision:
        print(f"\nReverification CQ1 revisee (Table 8) : {len(revision)} reponses")
        par = collections.defaultdict(list)
        for l in revision:
            v = None
            try:
                v = json.loads(re.search(r"\{.*\}", l.get("reponse_brute") or "", re.S).group(0))["verdict"]
            except Exception:
                pass
            par[(l["item_id"], l["modele_demande"])].append(v)
        for (it, mod), vs in sorted(par.items()):
            maj = 1 if sum(1 for v in vs if v == 1) * 2 > len(vs) else 0
            print(f"   {it:26} {mod:36} verdicts {vs}  majorite {maj}")
        with open(out / "revision_cq1.jsonl", "w", encoding="utf-8") as f:
            for l in revision:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
    retenues = [l for l in lignes if l["modele_demande"] not in exclus
                and l.get("variante") != "revision_v11"]
    n_exclues = len(lignes) - len(retenues) - len(revision)
    if n_exclues or revision:
        print(f"reponses exclues (modele retire du jury) : {n_exclues}")
        res = out / "resultats_retenus.jsonl"
        with open(res, "w", encoding="utf-8") as f:
            for l in retenues:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")
    if err and err.exists():
        e = [json.loads(l) for l in open(err, encoding="utf-8")]
        rattrapes = {l["empreinte"] for l in lignes}
        restants = {x["empreinte"]: x for x in e if x["empreinte"] not in rattrapes}
        print(f"echecs consignes : {len(e)}, dont non rattrapes : {len(restants)}",
              dict(collections.Counter(x["modele_demande"] for x in restants.values())))

    # --- chaine -------------------------------------------------------------
    lancer(ICI / "parse_results.py", "--fichier", res, "--sortie", out / "resultats_parses.csv", cwd=ICI)
    shutil.copy(ICI / "baselines_parses.csv", out / "baselines_parses.csv")
    lancer(ICI / "metrics.py", "--fichier", out / "resultats_parses.csv",
           "--fichier", out / "baselines_parses.csv", "--prefixe", str(out) + "/", cwd=ICI)
    lancer(ICI / "figures.py", "--metriques", out / "metriques_exploitable.csv",
           "--tests", out / "tests.csv", "--reponses", out / "resultats_parses.csv", cwd=out)
    print(f"\nTout est dans {out}")


if __name__ == "__main__":
    main()
