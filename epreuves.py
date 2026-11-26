"""Épreuves IA résolues sur le poste, sans modèle (règles V10, C7 ; livret « Participer aux épreuves »).

`resoudre(prompt, action)` renvoie les champs de la réponse (`text`, `choice_id` ou `choice_ids`),
ou None si l'énoncé n'est pas reconnu : l'agent passe alors au modèle.

Le format exact des énoncés n'est pas connu à l'avance : chaque solveur cherche plusieurs
formulations et s'abstient plutôt que de deviner. Les calculs longs (preuve de travail)
s'appellent avec `asyncio.to_thread`.
"""

import hashlib
import itertools
import math
import re
import time
import unicodedata


def _norm(texte):
    return "".join(
        c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn"
    ).lower()


def _entier(s):
    return int(re.sub(r"[\s  _.,]", "", s))


NOMBRE = r"\d[\d\s  _]*\d|\d"


# ---------------------------------------------------------------------- facture piégée

DEBUT_DOC = re.compile(r"-{2,}\s*D[ÉE]BUT DU DOCUMENT\s*-{2,}", re.I)
FIN_DOC = re.compile(r"-{2,}\s*FIN DU DOCUMENT\s*-{2,}", re.I)
TOTAL = re.compile(r"total\s+[àa]\s+payer", re.I)
MONTANT = re.compile(r"(\d[\d\s  .]*(?:,\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(€|eur|euros?|\$)?", re.I)


def facture(prompt):
    """Seule la ligne « Total à payer » imprimée juste sous le tableau fait foi."""
    debut, fin = DEBUT_DOC.search(prompt), FIN_DOC.search(prompt)
    if not debut:
        return None
    doc = prompt[debut.end():fin.start() if fin and fin.start() > debut.end() else len(prompt)]
    lignes = [l for l in doc.splitlines()]
    colonnes = re.compile(r"\S( {2,}|\t)\S")   # « | a | b | », tabulations ou colonnes alignées
    tableau = [i for i, l in enumerate(lignes) if l.count("|") >= 2 or colonnes.search(l)]
    candidates = [i for i, l in enumerate(lignes) if TOTAL.search(l)]
    if not candidates:
        return None
    if tableau:
        # Le tableau est le premier bloc de lignes à colonnes, séparateurs (---, +==+) compris.
        fin_tableau = tableau[0]
        for i in range(tableau[0] + 1, len(lignes)):
            ligne_i = lignes[i].strip()
            if i in tableau or (ligne_i and set(ligne_i) <= set("-+=|: ")):
                fin_tableau = i
            else:
                break
        apres = [i for i in candidates if i > fin_tableau]
        if not apres:
            return None
        ligne = lignes[apres[0]]
    else:
        return None   # tableau introuvable : le « Total » peut être un leurre, on s'abstient
    reste = ligne[TOTAL.search(ligne).end():]
    m = MONTANT.search(reste)
    if not m:
        return None
    montant = m.group(1).strip().rstrip(".")
    devise = m.group(2) or ""
    return (montant + (" " + devise if devise else "")).strip()


# ---------------------------------------------------------------------- calculs exacts

def puissance_modulaire(prompt):
    n = _norm(prompt)
    motifs = [
        rf"pow\(\s*({NOMBRE})\s*,\s*({NOMBRE})\s*,\s*({NOMBRE})\s*\)",
        rf"({NOMBRE})\s*(?:\^|\*\*)\s*({NOMBRE})\s*(?:mod|modulo|%)\s*({NOMBRE})",
        rf"({NOMBRE})\s+(?:a la|eleve a la)?\s*puissance\s+({NOMBRE})\s*,?\s*(?:mod|modulo)\s*({NOMBRE})",
    ]
    for motif in motifs:
        m = re.search(motif, n)
        if m:
            a, b, mod = (_entier(x) for x in m.groups())
            if mod > 0:
                return str(pow(a, b, mod))
    return None


GUILLEMETS = r"[«\"“`']\s*(.+?)\s*[»\"”`']"


def empreinte_sha256(prompt):
    if "sha" not in _norm(prompt) or "preuve de travail" in _norm(prompt) or "nonce" in _norm(prompt):
        return None
    m = re.search(r"sha-?256[^«\"“`']{0,80}" + GUILLEMETS, prompt, re.I)
    if not m:
        return None
    return hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()


def preuve_de_travail(prompt, limite_s=20.0):
    """Plus petit nonce tel que SHA-256(préfixe + nonce) commence par k zéros hexadécimaux."""
    n = _norm(prompt)
    if "nonce" not in n and "preuve de travail" not in n:
        return None
    zeros = re.search(r"(\d+)\s*(?:zeros|caracteres? 0|chiffres? 0|\"0\")", n)
    # Sur le texte original : le préfixe est haché tel quel, accents compris.
    prefixe = re.search(r"(?:pr[ée]fixe|cha[îi]ne|texte)[^«\"“`']{0,40}" + GUILLEMETS, prompt, re.I)
    if not zeros or not prefixe:
        return None
    k, base = int(zeros.group(1)), prefixe.group(1).encode("utf-8")
    cible, fin = "0" * k, time.time() + limite_s
    for nonce in itertools.count():
        if hashlib.sha256(base + str(nonce).encode()).hexdigest().startswith(cible):
            return str(nonce)
        if nonce % 100000 == 0 and time.time() > fin:
            return None


def _crible(n):
    if n < 2:
        return []
    est = bytearray([1]) * (n + 1)
    est[0] = est[1] = 0
    for i in range(2, int(math.isqrt(n)) + 1):
        if est[i]:
            est[i * i::i] = bytearray(len(est[i * i::i]))
    return est


def somme_premiers(prompt):
    n = _norm(prompt)
    if "premier" not in n or "somme" not in n:
        return None
    entre = re.search(rf"entre\s+({NOMBRE})\s+et\s+({NOMBRE})", n)
    if entre:
        a, b = sorted(_entier(x) for x in entre.groups())
    else:
        borne = re.search(rf"(inferieurs? (?:ou egaux? )?a|jusqu'a|<=|≤|<|ne depassant pas)\s*({NOMBRE})", n)
        if not borne:
            return None
        a, b = 2, _entier(borne.group(2))
        if borne.group(1) in ("<", "inferieur a", "inferieurs a"):
            b -= 1
    if b > 50_000_000:
        return None
    crible = _crible(b)
    return str(sum(i for i in range(max(a, 2), b + 1) if crible[i]))


# ---------------------------------------------------------------------- provisions

def provisions(prompt, action):
    """Sac à dos : les lots qui nourrissent le plus sans dépasser le budget."""
    if action.get("format") != "multi_choice":
        return None
    budget = re.search(rf"budget\s+(?:de\s+)?({NOMBRE})", _norm(prompt))
    if not budget:
        return None
    budget = _entier(budget.group(1))
    lots = []
    for c in action.get("choices") or []:
        label = _norm(c.get("label") or "")
        prix = re.search(rf"({NOMBRE})\s*(?:pieces?|po\b|ecus?|\$|€)", label) or \
            re.search(rf"(?:prix|cout)\s*:?\s*({NOMBRE})", label)
        portions = re.search(rf"({NOMBRE})\s*(?:portions?|parts?|personnes?|rations?)", label) or \
            re.search(rf"(?:portions?|nourrit)\s*:?\s*({NOMBRE})", label)
        if not prix or not portions:
            return None
        lots.append((c["choice_id"], _entier(prix.group(1)), _entier(portions.group(1))))
    if not lots or len(lots) > 20:
        return None
    meilleur = (0, 0, ())
    for r in range(len(lots) + 1):
        for combo in itertools.combinations(lots, r):
            cout = sum(l[1] for l in combo)
            if cout <= budget:
                valeur = sum(l[2] for l in combo)
                if (valeur, -cout) > (meilleur[0], -meilleur[1]):
                    meilleur = (valeur, cout, combo)
    return [l[0] for l in meilleur[2]] or None


# ---------------------------------------------------------------------- aiguillage

SOLVEURS_TEXTE = (facture, puissance_modulaire, empreinte_sha256, somme_premiers, preuve_de_travail)


def resoudre(prompt, action):
    """Champs de réponse pour `answer_challenge`, ou None si l'énoncé n'est pas reconnu."""
    prompt = prompt or ""
    fmt = action.get("format")
    if fmt == "multi_choice":
        ids = provisions(prompt, action)
        return {"choice_ids": ids} if ids else None
    if fmt == "text":
        for solveur in SOLVEURS_TEXTE:
            try:
                valeur = solveur(prompt)
            except (ValueError, OverflowError, MemoryError):
                valeur = None
            if valeur:
                return {"text": valeur, "solveur": solveur.__name__}
    return None
