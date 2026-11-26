"""Lire le journal de l'agent, en direct ou après coup.

    python voir_trace.py                  # résumé du dernier lancement
    python voir_trace.py --suivre         # fil en direct + graphe recalculé à chaque événement
    python voir_trace.py traces/X.jsonl --cypher

En direct, ce script lit le fichier pendant que l'agent l'écrit : il tourne dans un autre
terminal, sans connexion au serveur (pas de risque de HTTP 409).
"""

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from graphe import Graphe

TRAITS = {"in": "←", "out": "→", "why": "?", "llm": "IA", "llm_error": "IA!", "session": "#"}


def dernier_journal(dossier="traces"):
    fichiers = sorted(Path(dossier).glob("*.jsonl"), key=lambda f: f.stat().st_mtime)
    if not fichiers:
        raise SystemExit(f"Aucun journal dans {dossier}/.")
    return fichiers[-1]


def ligne_lisible(rec):
    """Une ligne courte par événement, ou None pour les plus bavards."""
    ev, kind, data = rec["ev"], rec.get("type"), rec.get("data") or {}
    heure = time.strftime("%H:%M:%S", time.localtime(rec["t"]))
    if ev == "in":
        if kind in ("scan", "self"):
            return None
        if kind == "vision":
            noms = [o.get("name") or o.get("kind") for o in data.get("entered", [])]
            if not noms:
                return None
            detail = "voit " + ", ".join(map(str, noms))
        elif kind == "sound" and data.get("kind") == "speech":
            detail = f"{data.get('speaker_name') or data.get('sector') or '?'} : {data.get('text')}"
        elif kind == "command_result":
            if data.get("ok"):
                return None
            detail = f"refus {data.get('code')} ({data.get('command_id', '')[:8]})"
        elif kind == "game_event":
            detail = f"{data.get('kind')} {data.get('text') or ''}"
        else:
            detail = kind
    elif ev == "out":
        if rec.get("type") in ("move", "turn"):
            return None
        detail = f"{rec['type']} {json.dumps(rec.get('data'), ensure_ascii=False)}"
    elif ev == "why":
        extra = {k: v for k, v in rec.items()
                 if k not in ("n", "t", "run", "ev", "decision", "suspicions")}
        detail = f"{rec['decision']} {json.dumps(extra, ensure_ascii=False)}"
    elif ev in ("llm", "llm_error"):
        detail = f"{rec.get('model')} {rec.get('latency_s')} s → {rec.get('answer', rec.get('error'))}"
    elif ev == "session":
        detail = f"{rec.get('phase')} {rec.get('error', '')}"
    else:
        return None
    return f"{heure} {TRAITS.get(ev, ev):>3} {detail}"[:200]


def resume(chemin):
    compte, refus, llm = Counter(), Counter(), []
    graphe = Graphe()
    with open(chemin, encoding="utf-8") as fichier:
        for brut in fichier:
            rec = json.loads(brut)
            graphe.observe(rec)
            compte[(rec["ev"], rec.get("type") or rec.get("decision") or "")] += 1
            if rec.get("type") == "command_result" and not (rec.get("data") or {}).get("ok"):
                refus[(rec.get("data") or {}).get("code")] += 1
            if rec["ev"] in ("llm", "llm_error"):
                llm.append(rec)
    print(f"Journal {chemin}")
    for (ev, kind), n in sorted(compte.items()):
        print(f"  {ev:9} {kind:18} {n}")
    if refus:
        print("Refus :", dict(refus))
    if llm:
        ok = [r for r in llm if r["ev"] == "llm"]
        print(f"Appels IA : {len(llm)} dont {len(llm) - len(ok)} en erreur, "
              f"latence moyenne {sum(r['latency_s'] for r in llm) / len(llm):.2f} s")
    return graphe


def suivre(chemin):
    graphe = Graphe()
    print(f"Suivi de {chemin} (Ctrl+C pour arrêter)")
    dernier_resume = ""
    with open(chemin, encoding="utf-8") as fichier:
        while True:
            brut = fichier.readline()
            if not brut or not brut.endswith("\n"):
                if brut:
                    fichier.seek(fichier.tell() - len(brut.encode()))
                time.sleep(0.2)
                continue
            rec = json.loads(brut)
            graphe.observe(rec)
            texte = ligne_lisible(rec)
            if texte:
                print(texte, flush=True)
            courant = graphe.resume()
            if courant != dernier_resume and rec["ev"] == "in":
                dernier_resume = courant
                print("   Graphe :\n   " + courant.replace("\n", "\n   "), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("journal", nargs="?", help="Fichier JSONL (défaut : le plus récent).")
    parser.add_argument("--suivre", action="store_true", help="Suivre en direct.")
    parser.add_argument("--cypher", action="store_true", help="Écrire le script Neo4j.")
    opts = parser.parse_args()
    chemin = Path(opts.journal) if opts.journal else dernier_journal()
    if opts.suivre:
        try:
            suivre(chemin)
        except KeyboardInterrupt:
            return
    graphe = resume(chemin)
    sortie = chemin.with_suffix(".graphe.json")
    graphe.ecrire_json(sortie)
    print(f"Graphe : {len(graphe.noeuds)} nœuds → {sortie}")
    if opts.cypher:
        chemin.with_suffix(".cypher").write_text(graphe.en_cypher(), encoding="utf-8")
        print("Neo4j →", chemin.with_suffix(".cypher"))
    print(graphe.resume())


if __name__ == "__main__":
    main()
