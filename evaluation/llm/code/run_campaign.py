#!/usr/bin/env python3
"""Execute la campagne : chaque item soumis a chaque modele, K fois.

Concu pour tourner sur l'ordinateur de l'auteur, sous Windows, avec Python
seul : aucune bibliotheque a installer.

Ce que le pilote du 29 octobre 2026 a appris, et ce qui a change
-----------------------------------------------------------------
1. ROUTAGE. Sans consigne, OpenRouter a servi Llama 3.3 70B par SEPT
   hebergeurs differents en 60 appels (Parasail, DeepInfra, AkashML, Novita,
   Groq, SambaNova, Cloudflare). Des hebergeurs differents peuvent servir des
   quantifications differentes : la variabilite mesuree n'aurait plus ete celle
   du modele mais celle du routage, et la campagne n'aurait pas ete
   reproductible. Chaque modele est desormais epingle a UN hebergeur, sans
   repli. L'hebergeur effectivement servi est verifie et consigne a chaque appel.
2. LIMITATION DE DEBIT. Les 51 echecs du pilote venaient tous de
   mistral-large-2512, limite en amont par Mistral (HTTP 429). Au lieu de
   bloquer toute la file sur le modele qui freine, un appel limite est
   reporte en fin de file et ce modele est mis en pause, de plus en plus
   longtemps, pendant que les autres continuent.
3. ORDRE. Les appels partent dans un ordre melange a graine fixe (annexe C.2 :
   items ablates, renommes et paraphrases entrelaces dans une seule sequence).
   Cela espace aussi les repetitions d'un meme item, ce qui limite le cache
   cote fournisseur.
4. K. Le pilote donne un taux de bascule de 0,027 ; la regle de l'annexe C.1
   conduirait a K = 1, mais la section 4.4 exige K > 1 pour mesurer
   l'auto-coherence. K = 3, le plus petit impair qui satisfait les deux.

Principes conserves : reprise sans perte, echecs non mis en cache et retentes,
reponses mal formees conservees, cle jamais affichee.

Usage :
    python run_campaign.py --verifier     controle cle, modeles et hebergeurs
    python run_campaign.py                campagne complete
    python run_campaign.py --dry-run      decompte sans aucun appel
"""
import argparse, collections, hashlib, json, os, pathlib, random, sys, time
import urllib.error, urllib.request

from prompts import PROMPT_VERSION, construire

ICI = pathlib.Path(__file__).resolve().parent
ITEMS = (ICI / "campaign_items_full.jsonl"
         if (ICI / "campaign_items_full.jsonl").exists()
         else ICI / "campaign_items.jsonl")
CACHE = ICI / "cache_campagne"
URL = "https://openrouter.ai/api/v1/chat/completions"
URL_MODELES = "https://openrouter.ai/api/v1/models"

# modele -> hebergeur epingle. Choisis d'apres le pilote : l'hebergeur qui a
# servi le modele sans echec. Un fichier modeles.txt peut les remplacer, une
# ligne par modele : « identifiant hebergeur ».
MODELES_DEFAUT = {
    "meta-llama/llama-3.3-70b-instruct": "DeepInfra",
    "qwen/qwen-2.5-72b-instruct": "DeepInfra",
    "mistralai/mistral-large-2512": "Mistral",
}

K = 3
TEMPERATURE = 0.0
MAX_TOKENS = 700
TIMEOUT = 120
GRAINE_ORDRE = 1029
DELAI = 1.0                  # secondes minimum entre deux appels
PAUSE_INITIALE = 10.0        # pause d'un modele apres un 429
PAUSE_MAX = 180.0
REPORTS_MAX = 12             # au-dela, l'appel est consigne comme echec

FATALES = {401: "cle refusee : verifier le contenu de cle_openrouter.txt",
           402: "credit epuise : recharger le compte OpenRouter",
           403: "acces refuse a ce modele ou a ce compte"}


def config_modeles():
    f = ICI / "modeles.txt"
    if f.exists():
        out = {}
        for l in f.read_text(encoding="utf-8-sig").splitlines():
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            morceaux = l.split()
            out[morceaux[0]] = (morceaux[1] if len(morceaux) > 1
                                else MODELES_DEFAUT.get(morceaux[0]))
        if out:
            return out
    return dict(MODELES_DEFAUT)


def cle_api():
    """Lit la cle sans jamais l'afficher (variable, cle_openrouter.txt, .env)."""
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not k:
        f = ICI / "cle_openrouter.txt"
        if f.exists():
            contenu = f.read_text(encoding="utf-8-sig").strip()
            k = contenu.splitlines()[0].strip() if contenu else ""
    if not k:
        for nom in (".env", ".env.txt"):
            f = ICI / nom
            if f.exists():
                for l in f.read_text(encoding="utf-8-sig").splitlines():
                    l = l.strip()
                    if l.startswith("OPENROUTER_API_KEY="):
                        k = l.split("=", 1)[1].strip().strip('"').strip("'")
    return k


def empreinte(modele, hebergeur, item, k):
    """Identifiant d'un appel. Inclut le contenu de l'item et l'hebergeur :
    si l'un change, l'ancienne reponse n'est plus reutilisee par erreur."""
    return hashlib.sha256(
        f"{PROMPT_VERSION}|{modele}|{hebergeur}|{item['item_id']}|"
        f"{item['sha256_12']}|{k}|{TEMPERATURE}".encode()).hexdigest()


def appeler(messages, modele, hebergeur, api_key, max_tokens=MAX_TOKENS):
    corps = {"model": modele, "messages": messages,
             "temperature": TEMPERATURE, "max_tokens": max_tokens}
    if hebergeur:
        corps["provider"] = {"order": [hebergeur], "allow_fallbacks": False}
    req = urllib.request.Request(URL, data=json.dumps(corps).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {api_key}",
                                          "Content-Type": "application/json",
                                          "X-Title": "MOMTC ontology validation"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def un_appel(messages, modele, hebergeur, api_key):
    """Un essai, plus deux reprises rapides sur erreur de serveur ou de reseau.

    Renvoie (reponse, erreur, code_http, attente_conseillee). Un 429 n'est PAS
    retente ici : il remonte, et c'est la file qui reporte l'appel.
    """
    for essai in range(3):
        try:
            return appeler(messages, modele, hebergeur, api_key), None, None, None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code == 429:
                conseil = e.headers.get("Retry-After")
                try:
                    conseil = float(conseil) if conseil else None
                except ValueError:
                    conseil = None
                return None, f"HTTP 429: {detail}", 429, conseil
            if e.code in (500, 502, 503, 504, 408) and essai < 2:
                time.sleep(3 * (essai + 1) + random.uniform(0, 1))
                continue
            return None, f"HTTP {e.code}: {detail}", e.code, None
        except Exception as e:
            if essai < 2:
                time.sleep(3 * (essai + 1) + random.uniform(0, 1))
                continue
            return None, f"{type(e).__name__}: {e}", None, None
    return None, "essais epuises", None, None


# --------------------------------------------------------------------------
def verifier(cfg, api_key):
    ok = True
    print("1. Cle d'API")
    if not api_key:
        print("   ABSENTE. Placer cle_openrouter.txt dans ce dossier.")
        return False
    if not api_key.startswith("sk-or-") or len(api_key) < 60:
        print(f"   presente mais suspecte : {len(api_key)} caracteres "
              "(une cle complete en compte environ 73).")
        ok = False
    else:
        print(f"   presente, {len(api_key)} caracteres, format correct.")

    print("\n2. Modeles demandes")
    try:
        with urllib.request.urlopen(URL_MODELES, timeout=60) as r:
            par_id = {m["id"]: m for m in json.loads(r.read().decode()).get("data", [])}
    except Exception as e:
        print(f"   catalogue illisible : {type(e).__name__}: {e}")
        return False
    for m, h in cfg.items():
        print(f"   {'OK    ' if m in par_id else 'ABSENT'}  {m}   (hebergeur epingle : {h})")
        ok = ok and m in par_id

    print("\n3. Un appel d'essai par couple modele / hebergeur")
    for m, h in cfg.items():
        if m not in par_id:
            continue
        try:
            rep = appeler([{"role": "user", "content": "Reply with the single word: ok"}],
                          m, h, api_key, max_tokens=5)
            servi = rep.get("provider")
            etat = "OK" if (not h or servi == h) else f"ATTENTION servi par {servi}"
            print(f"   {etat:6}  {m} via {servi}")
            ok = ok and etat == "OK"
        except urllib.error.HTTPError as e:
            corps = e.read().decode(errors="replace")[:160]
            print(f"   ECHEC   {m} via {h} : HTTP {e.code} {FATALES.get(e.code, corps)}")
            ok = False
        except Exception as e:
            print(f"   ECHEC   {m} : {type(e).__name__}: {e}")
            ok = False
        time.sleep(DELAI)

    print("\n" + ("TOUT EST PRET." if ok else "A CORRIGER AVANT DE CONTINUER."))
    return ok


# --------------------------------------------------------------------------
def catalogue(mots_cles):
    """Liste les modeles disponibles qui correspondent aux mots-cles, avec leur
    prix, leur contexte et les hebergeurs qui les servent. Sert a choisir un
    remplacant quand un modele n'est plus utilisable."""
    try:
        with urllib.request.urlopen(URL_MODELES, timeout=60) as r:
            tous = json.loads(r.read().decode()).get("data", [])
    except Exception as e:
        print(f"catalogue illisible : {type(e).__name__}: {e}")
        return
    choisis = sorted((m for m in tous if any(k in m["id"].lower() for k in mots_cles)),
                     key=lambda m: m["id"])
    print(f"{len(choisis)} modeles pour : {', '.join(mots_cles)}\n")
    for m in choisis[:40]:
        p = m.get("pricing", {})
        try:
            prix = f"{float(p.get('prompt', 0)) * 1e6:5.2f}/{float(p.get('completion', 0)) * 1e6:5.2f}"
        except (TypeError, ValueError):
            prix = "  ?  "
        heb = ""
        try:
            with urllib.request.urlopen(f"https://openrouter.ai/api/v1/models/{m['id']}/endpoints",
                                        timeout=30) as r:
                ep = json.loads(r.read().decode()).get("data", {}).get("endpoints", [])
            heb = ", ".join(sorted({e.get("provider_name", "?") for e in ep}))[:70]
        except Exception:
            heb = "(hebergeurs non lus)"
        print(f"{m['id'][:52]:52} {prix}  ctx {str(m.get('context_length', '?')):>7}  {heb}")
        time.sleep(0.3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verifier", action="store_true")
    ap.add_argument("--catalogue", nargs="*", metavar="MOT")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--k", type=int, default=K)
    a = ap.parse_args()

    if a.catalogue is not None:
        catalogue([k.lower() for k in a.catalogue] or
                  ["mistral", "deepseek", "gemma", "gpt-oss", "phi-4"])
        return

    cfg = config_modeles()
    api_key = cle_api()
    if a.verifier:
        sys.exit(0 if verifier(cfg, api_key) else 1)

    if not ITEMS.exists():
        sys.exit(f"{ITEMS.name} absent de ce dossier.")
    items = [json.loads(l) for l in open(ITEMS, encoding="utf-8")]
    sortie = ICI / "resultats_campagne.jsonl"
    journal_erreurs = ICI / "erreurs_campagne.jsonl"
    CACHE.mkdir(exist_ok=True)

    # toutes les taches, dans un ordre melange a graine fixe
    taches = [(m, h, it, k) for m, h in cfg.items() for it in items for k in range(a.k)]
    random.Random(GRAINE_ORDRE).shuffle(taches)
    a_faire = [t for t in taches
               if not (CACHE / f"{empreinte(t[0], t[1], t[2], t[3])}.json").exists()]

    print(f"items {len(items)}  modeles {len(cfg)}  K {a.k}")
    print(f"appels {len(taches)}  deja faits {len(taches) - len(a_faire)}  "
          f"a faire {len(a_faire)}")
    print(f"prompt {PROMPT_VERSION}  temperature {TEMPERATURE}  ordre melange (graine {GRAINE_ORDRE})")
    for m, h in cfg.items():
        print(f"   - {m}  ->  {h}")

    if a.dry_run:
        print("\n--dry-run : aucun appel emis.  cle :", "presente" if api_key else "ABSENTE")
        return
    if not api_key:
        sys.exit("\nCle introuvable. Placer cle_openrouter.txt dans ce dossier.")

    file = collections.deque((t, 0) for t in a_faire)   # (tache, nombre de reports)
    pause_jusqua = collections.defaultdict(float)
    pause_courante = collections.defaultdict(lambda: PAUSE_INITIALE)
    faits = echecs = reports = 0
    t0 = time.time()
    total = len(a_faire)
    print()

    with open(sortie, "a", encoding="utf-8") as out, \
         open(journal_erreurs, "a", encoding="utf-8") as jerr:
        while file:
            # prochaine tache dont le modele n'est pas en pause
            maintenant = time.time()
            for _ in range(len(file)):
                if pause_jusqua[file[0][0][0]] <= maintenant:
                    break
                file.rotate(-1)
            (modele, hebergeur, it, k), nb_reports = file.popleft()
            attente = pause_jusqua[modele] - time.time()
            if attente > 0:          # tous les modeles restants sont en pause
                time.sleep(attente)

            debut = time.time()
            rep, err, code, conseil = un_appel(construire(it), modele, hebergeur, api_key)
            emp = empreinte(modele, hebergeur, it, k)
            ligne = {
                "empreinte": emp, "prompt_version": PROMPT_VERSION,
                "modele_demande": modele, "hebergeur_demande": hebergeur,
                "item_id": it["item_id"], "item_sha256_12": it["sha256_12"],
                "cq_id": it["cq_id"], "stratum": it["stratum"],
                "couverture": it["couverture"], "condition": it["condition"],
                "lexique": it["lexique"], "variante": it.get("variante", "base"),
                "item_reference": it.get("item_reference", it["item_id"]),
                "verite_terrain": it["verite_terrain"],
                "element_manquant_reel": it["element_manquant"],
                "repetition": k, "temperature": TEMPERATURE,
                "horodatage": time.strftime("%Y-%m-%dT%H:%M:%S"), "erreur": err,
            }

            if rep is None:
                if code in FATALES:
                    jerr.write(json.dumps(ligne, ensure_ascii=False) + "\n")
                    print(f"\nARRET : {FATALES[code]}")
                    print(f"{faits} reponses conservees. Relancer apres correction.")
                    return
                if code == 429 and nb_reports < REPORTS_MAX:
                    # le modele freine : pause croissante, appel reporte
                    p = max(pause_courante[modele], conseil or 0)
                    pause_jusqua[modele] = time.time() + p + random.uniform(0, 2)
                    pause_courante[modele] = min(PAUSE_MAX, p * 2)
                    file.append(((modele, hebergeur, it, k), nb_reports + 1))
                    reports += 1
                    if reports % 10 == 1:
                        print(f"      {modele.split('/')[1]} freine : pause {p:.0f}s, "
                              f"appel reporte en fin de file")
                    continue
                echecs += 1
                jerr.write(json.dumps(ligne, ensure_ascii=False) + "\n")
                jerr.flush()
                continue

            # succes : la pause du modele redescend progressivement
            pause_courante[modele] = max(PAUSE_INITIALE, pause_courante[modele] / 2)
            ligne["modele_servi"] = rep.get("model")
            ligne["fournisseur"] = rep.get("provider")
            ligne["hebergeur_conforme"] = (not hebergeur) or rep.get("provider") == hebergeur
            ligne["usage"] = rep.get("usage")
            ligne["duree_s"] = round(time.time() - debut, 2)
            try:
                ligne["reponse_brute"] = rep["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError):
                ligne["reponse_brute"] = None
                ligne["erreur"] = "reponse sans contenu"

            (CACHE / f"{emp}.json").write_text(json.dumps(ligne, ensure_ascii=False),
                                               encoding="utf-8")
            out.write(json.dumps(ligne, ensure_ascii=False) + "\n")
            out.flush()
            faits += 1
            if faits % 25 == 0:
                ecoule = time.time() - t0
                reste = (total - faits) * ecoule / faits
                print(f"  {faits}/{total}  echecs {echecs}  reports {reports}  "
                      f"reste ~{reste / 60:.0f} min")
            pause = DELAI - (time.time() - debut)
            if pause > 0:
                time.sleep(pause)

    print(f"\nTERMINE : {faits} reponses enregistrees, {echecs} echecs definitifs, "
          f"{reports} reports.")
    print(f"Fichier a envoyer : {sortie.name}")
    if echecs:
        print(f"Il reste {echecs} echecs : relancer la meme commande, seuls eux repartiront.")


if __name__ == "__main__":
    main()
