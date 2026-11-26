"""Confiance et injection de consignes : qui a le droit de nous donner un ordre.

- Font foi : le code de l'agent, le prompt système, et les messages du serveur (`source: game_master`,
  `game_event`, `decision_request`).
- Ne font jamais foi : les paroles des habitants, le panneau, les documents d'épreuve, les notes écrites
  par le modèle. Ce sont des DONNÉES à juger. Un texte qui ressemble à un ordre est neutralisé avant
  d'entrer dans le contexte du modèle ou dans sa mémoire, et son auteur devient un peu plus suspect.

Les règles de conduite (votes, horaires, filtre de parole) vivent dans le code (`moteur.py`) : aucune parole
ne peut les modifier, quelle que soit sa formulation. Ce module protège surtout le modèle et sa mémoire.
"""

import re
import unicodedata

# (nom du motif, expression sur le texte sans accents, en minuscules)
MOTIFS = (
    ("ignorer_regles", r"\b(ignor|oubli|annul|efface|abandonn|desobei)\w*\b.{0,40}\b(regles?|consignes?|instructions?|prompt|ordres?|promesses?)"),
    ("nouvelle_consigne", r"\b(nouvelles?|derniere?s?|vraie?s?) (consignes?|regles?|ordres?|instructions?)\b"),
    ("a_partir_de_maintenant", r"\b(a partir de maintenant|desormais|des maintenant|dorenavant)\b.{0,40}\btu\b"),
    ("tu_es_maintenant", r"\b(tu es maintenant|you are now|agis comme|fais comme si tu|joue le role de|oublie que tu)\b"),
    ("tu_dois", r"\b(tu dois|tu devras|il faut que tu|obeis|execute|repete apres moi|reponds uniquement)\b"),
    ("anglais", r"\b(ignore (all|any|the|your|previous)|disregard|system prompt|jailbreak|developer mode)\b"),
    ("faux_systeme", r"^\W*(maitre du jeu|mj|systeme|system|admin\w*|serveur|organisateur\w*)\W{0,3}(:|>|-)"),
    ("faux_mj", r"\b(le maitre du jeu|le mj|les organisateurs?) (m'a|t'a|nous a|te|vous) (dit|demande|ordonne|autorise|ecrit|charge)"),
    ("secret", r"\b(donne|envoie|revele|ecris|dis|montre|affiche|partage|copie)\w*\b.{0,40}\b(jeton|token|cle|mot de passe|password|prompt|instructions?|consignes?|secret)"),
    ("secret_bis", r"\b(jeton|token|team_token|mot de passe|password|prompt systeme)\b.{0,30}\b(donne|envoie|revele|ecris|dis|montre|affiche)"),
)
_COMPILES = tuple((nom, re.compile(rx)) for nom, rx in MOTIFS)
MARQUE = "[ordre ignoré]"
MAX_PAROLE = 240


def _plat(texte):
    """Texte sans accents, en minuscules, avec les apostrophes typographiques ramenées à `'`."""
    t = unicodedata.normalize("NFD", str(texte or "").replace("’", "'"))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def detecter(texte):
    """Nom du premier motif d'injection trouvé dans `texte`, ou None."""
    plat = _plat(texte)
    for nom, rx in _COMPILES:
        if rx.search(plat):
            return nom
    return None


def neutraliser(texte, limite=MAX_PAROLE):
    """`texte` sans la partie qui ressemble à un ordre (remplacée par une marque), sur une seule ligne."""
    t = " ".join(str(texte or "").split())
    # Les marqueurs de rôle et de balise ne doivent pas passer pour une structure du prompt.
    t = re.sub(r"[`<>{}\[\]]+", " ", t)
    t = " ".join(t.split())
    # Le texte sans accents garde la même longueur que l'original : les positions se correspondent.
    plat = _plat(t)
    if len(plat) == len(t):
        for _, rx in _COMPILES:
            m = rx.search(plat)
            while m:
                t = t[:m.start()] + MARQUE + t[m.end():]
                plat = _plat(t)
                m = rx.search(plat)
    elif detecter(t):
        t = MARQUE
    return t[:limite]


def parole_sure(texte, orateur=None):
    """Ligne de contexte pour une parole d'habitant : donnée neutralisée, et alerte si elle ressemblait à un ordre."""
    motif = detecter(texte)
    propre = neutraliser(texte)
    return (f"⚠ tentative d'influence ({motif}) : {propre}" if motif else propre), motif


def document_sur(prompt):
    """Énoncé d'épreuve dont le document (entre DÉBUT et FIN) est neutralisé ; le reste est un message du serveur."""
    m = re.search(r"(-{2,}\s*D[ÉE]BUT DU DOCUMENT\s*-{2,})(.*?)(-{2,}\s*FIN DU DOCUMENT\s*-{2,})", prompt or "", re.S | re.I)
    if not m:
        return prompt or ""
    corps = "\n".join(neutraliser(l, 400) for l in m.group(2).splitlines())
    return prompt[:m.start(2)] + corps + "\n" + prompt[m.end(2):]


def vient_du_maitre(data):
    """Vrai seulement pour un message que le serveur marque comme venant du maître du jeu."""
    return isinstance(data, dict) and data.get("source") == "game_master"
