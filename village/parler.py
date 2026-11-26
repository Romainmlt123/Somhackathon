"""Compétence « parler » : quand l'agent parle, une réplique de `Régles/random_sentences.md` s'ajoute au hasard à son texte.

    texte, ajout = habiller("Léa, où étais-tu ce soir ?")      # ajout : la réplique ajoutée, ou None

Le fichier est une liste de répliques séparées par des lignes vides ; un bloc écrit sur plusieurs lignes ne fait qu'une réplique.
Le texte final respecte la règle « Porter la voix » (240 caractères au plus) : une réplique trop longue pour la place restante
n'est jamais retenue. L'appelant peut aussi écarter des répliques avec `accepte` (par exemple celles que `moteur.nettoyer`
ferait taire pour un loup), pour qu'une réplique ne réduise jamais l'agent au silence.
"""
import random
import re
from pathlib import Path

import moteur

FICHIER = Path(__file__).parent.parent / "Régles" / "random_sentences.md"
PROBA = 1.0          # chance d'ajouter une réplique à chaque prise de parole (1 = toujours)

_cache = {}          # (chemin, date de modification) -> répliques


def charger(chemin=FICHIER):
    """Les répliques du fichier, relues si le fichier change. Fichier absent ou illisible : aucune réplique, jamais d'erreur."""
    chemin = Path(chemin)
    try:
        cle = (chemin, chemin.stat().st_mtime_ns)
        if cle not in _cache:
            blocs = re.split(r"\n\s*\n", chemin.read_text(encoding="utf-8"))
            _cache.clear()
            _cache[cle] = [" ".join(ligne.strip() for ligne in b.splitlines() if ligne.strip()) for b in blocs if b.strip()]
        return _cache[cle]
    except OSError:
        return []


def habiller(texte, accepte=None, rng=random, proba=PROBA, chemin=FICHIER):
    """Renvoie (texte final, réplique ajoutée ou None). La réplique est placée avant ou après le texte, au hasard."""
    texte = " ".join(str(texte or "").split())
    if not texte or rng.random() >= proba:
        return texte, None
    place = moteur.PAROLE_MAX - len(texte) - 1
    candidates = [p for p in charger(chemin) if len(p) <= place and (accepte is None or accepte(p))]
    if not candidates:
        return texte, None
    phrase = rng.choice(candidates)
    return (f"{texte} {phrase}" if rng.random() < 0.5 else f"{phrase} {texte}"), phrase
