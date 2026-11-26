"""Moteur de décision de l'habitant.

Applique les règles de conduite de `Régles/ETUDE_LOUP_GAROU.md` (C1-C9, V1-V12, L1-L13)
sans réseau ni modèle : `agent.py` lui transmet ce que l'habitant perçoit et exécute ce
qu'il rend. Chaque décision porte le numéro de la règle appliquée, repris dans `journal.why`.

Ce qui reste au modèle, en option (`appel_modele.py`) : départager un vote incertain,
reformuler une réponse quand on est interpellé, et les épreuves que `epreuves.py` ne
sait pas calculer.
"""

import random
import re
import time
import unicodedata
from dataclasses import dataclass

import confiance

# Heures du village, en minutes depuis minuit (Régles/LIVRET.md, aide-mémoire chiffré).
REVEIL = 8 * 60
ANNONCE_EPREUVE = 14 * 60
CONSEIL = 17 * 60
VOTE_DEBUT = 19 * 60
VOTE_FIN = 21 * 60
NUIT = 22 * 60
FIN_CHASSE = 6 * 60

MARGE_VOTE_S = 10        # C3 : bulletin au plus tard 10 s avant la clôture
PAROLE_MAX = 240         # C5
PAROLE_ECART_S = 2.2     # C5 : environ 2 s entre deux paroles
PORTEE_ACTION_M = 1.8    # sit, transform, attack : 2 m, avec une marge

# V7 : on ne pousse pas l'élimination d'une Voyante ou Sorcière déclarée en dessous.
SEUIL_PREUVE = 0.75
# V9 : la Sorcière n'empoisonne qu'au-dessus.
SEUIL_POISON = 0.8

# C9 : une personnalité constante, reprise dans tous les prompts.
PERSONNALITE = (
    "Tu es un ancien du village, calme, précis et un peu pince-sans-rire. Tu parles par "
    "phrases courtes, tu cites ce que tu as vu avec l'heure, et tu te méfies des beaux discours."
)

# L4 : ce qu'un loup ne dit jamais, parce qu'un villageois ne peut pas le savoir.
MOTS_INTERDITS_LOUP = (
    "la pierre", "clairiere", "transform", "meute", "chasse", "j'ai tue", "on a tue",
    "nous avons tue", "mon partenaire", "ma partenaire", "nous les loups", "notre victime",
)

# V5 : une accusation qui cite un de ces marqueurs s'appuie sur un fait.
MARQUEURS_FAIT = re.compile(
    r"\b(vu|vue|entendu|\d{1,2} ?h|nuit|pres d|devant|chez|pierre|cadavre|corps|indice|"
    r"inspect|vote|voyante)"
)
MOTS_ACCUSATION = ("loup", "suspect", "menteur", "menteuse", "coupable", "vote contre",
                   "votez contre", "eliminez", "accuse")

# V4 : indices du graphe qui sont des observations directes, donc dicibles.
FAITS_VUS = {"vu_pres_pierre_nuit", "vu_pres_cadavre", "debout_dehors_nuit"}
LIEUX_DITS = {
    "stone": "près de la pierre de la clairière",
    "campfire": "près du feu",
    "board": "près du panneau",
    "chapel": "près de la chapelle",
    "canteen": "près de la cantine",
}


def normaliser(texte):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(texte or "").replace("’", "'"))
        if unicodedata.category(c) != "Mn"
    ).lower()


def role_de(role):
    """Rôle du protocole ramené à : loup, voyante, sorciere, villageois, ou None."""
    r = normaliser(role).strip()
    if not r:
        return None
    if r in ("loup", "wolf", "werewolf", "loup-garou", "loup garou"):
        return "loup"
    if r in ("voyante", "seer"):
        return "voyante"
    if r in ("sorciere", "witch"):
        return "sorciere"
    return "villageois"


def forme_loup(forme):
    return normaliser(forme) in ("wolf", "loup")


def nuit(minute):
    return minute is not None and (minute >= NUIT or minute < REVEIL)


def heure(minute):
    return "??:??" if minute is None else f"{minute // 60:02d}:{minute % 60:02d}"


# ---------------------------------------------------------------------- où aller

@dataclass
class Objectif:
    lieu: str | None   # kind ou nom d'un repère, ou "maison", ou "chasse", ou None (libre)
    regle: str
    motif: str


def objectif(minute, role, forme, epreuve_lieu=None, scrutin_ouvert=False, chasse_finie=False):
    """Où l'habitant doit être maintenant (C1, C4, V1, L1, L3)."""
    if minute is None:
        return Objectif(None, "-", "heure inconnue")
    if role_de(role) == "loup" and (minute >= NUIT or minute < FIN_CHASSE):
        if chasse_finie:
            return Objectif("maison", "L3", "chasse finie : rentrer avant le réveil")
        if forme_loup(forme):
            return Objectif("chasse", "L1", "transformé : chasser les habitants dehors")
        return Objectif("stone", "L1", "nuit : se transformer à la pierre")
    if nuit(minute):
        regle = "L3" if role_de(role) == "loup" else "V1"
        return Objectif("maison", regle, "nuit : être chez soi, couché")
    if scrutin_ouvert:
        return Objectif("campfire", "C1", "scrutin ouvert : rejoindre le feu")
    if epreuve_lieu:
        return Objectif(epreuve_lieu, "C4", "épreuve annoncée : y aller et rester")
    if CONSEIL <= minute < VOTE_FIN:
        return Objectif("campfire", "C1", "conseil : être au feu avant 19 h")
    return Objectif(None, "-", "temps libre")


# ---------------------------------------------------------------------- choix

@dataclass
class Choix:
    choice_id: str | None
    regle: str
    motif: str
    sur: bool = True   # False : le modèle peut être consulté pour départager


def _fiches(graphe, choix):
    fiches = []
    for c in choix:
        jid = graphe.id_joueur(c.get("label") or "")
        fiches.append({
            "choice_id": c.get("choice_id"),
            "label": c.get("label"),
            "p": graphe.proba_loup(jid),
            "certain": graphe.certain.get(jid),
            "accus": graphe.nb_accusations(jid),
            "pretend": graphe.pretentions(jid),
        })
    return fiches


def _choisi(fiche, regle, motif, sur=True):
    return Choix(fiche["choice_id"], regle,
                 f"{motif} : {fiche['label']} (p loup {fiche['p']:.2f}, {fiche['accus']} accusations)",
                 sur)


def choisir_vote(graphe, moi, role, choix, kind="council_vote"):
    """Bulletin du conseil ou de l'élection du Capitaine (C2, V2, V7, L9, L10)."""
    fiches = [f for f in _fiches(graphe, choix) if f["label"] != moi]   # C2
    if not fiches:
        return Choix(None, "C2", "aucun candidat autre que soi")
    plus_suspect = lambda f: (-f["p"], -f["accus"], random.random())
    plus_fiable = lambda f: (f["p"], f["accus"], random.random())

    if role_de(role) == "loup":
        partenaires = [f for f in fiches if f["certain"] == "role:loup"]
        autres = [f for f in fiches if f["certain"] != "role:loup"]
        if kind == "captain_election":
            if partenaires:
                return _choisi(partenaires[0], "L10", "Capitaine : un loup")
            return _choisi(min(autres, key=lambda f: (f["accus"], f["label"] or "")),
                           "L7", "Capitaine : le moins exposé")
        max_accus = max(f["accus"] for f in fiches)
        condamnes = [f for f in partenaires if f["accus"] >= 2 and f["accus"] == max_accus]
        if condamnes:
            return _choisi(condamnes[0], "L9", "partenaire déjà condamné : voter avec le village")
        if not autres:
            return _choisi(max(partenaires, key=lambda f: f["accus"]), "L9", "seuls des loups")
        pouvoirs = [f for f in autres if f["pretend"] & {"voyante", "sorciere"}]
        cible = pouvoirs or autres
        return _choisi(max(cible, key=lambda f: (f["accus"], -f["p"])), "L10",
                       "rôle à pouvoir déclaré" if pouvoirs else "villageois le plus accusé")

    if kind == "captain_election":
        return _choisi(min(fiches, key=plus_fiable), "V2", "Capitaine : le moins suspect")
    certains = [f for f in fiches if f["certain"] == "role:loup"]
    if certains:
        return _choisi(certains[0], "V2", "loup certain")
    eligibles = [f for f in fiches if f["certain"] in (None, "role:loup")] or fiches
    proteges = [f for f in eligibles
                if f["pretend"] & {"voyante", "sorciere"} and f["p"] < SEUIL_PREUVE]
    restants = [f for f in eligibles if f not in proteges] or eligibles
    meilleur = min(restants, key=plus_suspect)
    regle = "V7" if proteges and meilleur not in proteges else "V2"
    return _choisi(meilleur, regle, "le plus suspect du carnet", sur=meilleur["p"] >= 0.5)


def choisir_inspection(graphe, moi, choix):
    """Voyante : inspecter le plus suspect dont le rôle n'est pas connu (V8)."""
    fiches = [f for f in _fiches(graphe, choix) if f["label"] != moi and not f["certain"]]
    if not fiches:
        fiches = [f for f in _fiches(graphe, choix) if f["label"] != moi]
    if not fiches:
        return Choix(None, "V8", "aucun candidat")
    return _choisi(max(fiches, key=lambda f: (f["p"], f["accus"])), "V8", "inspecter le plus suspect")


def choisir_potion(graphe, moi, actions, allow_abstain=True):
    """Sorcière : sauver la victime, empoisonner seulement sur preuve (V9).

    Renvoie (action, choice_id, regle, motif) ; action None si rien à faire.
    """
    par_nom = {a.get("action"): a for a in actions}
    soin = par_nom.get("heal")
    if soin and soin.get("choices"):
        c = soin["choices"][0]
        return "heal", c["choice_id"], "V9", f"sauver la victime de la nuit : {c.get('label')}"
    poison = par_nom.get("poison")
    if poison and poison.get("choices"):
        fiches = [f for f in _fiches(graphe, poison["choices"]) if f["label"] != moi]
        sures = [f for f in fiches if f["certain"] == "role:loup" or f["p"] >= SEUIL_POISON]
        if sures:
            f = max(sures, key=lambda f: f["p"])
            return "poison", f["choice_id"], "V9", f"loup confirmé par les faits : {f['label']}"
    if allow_abstain:
        return "abstain", None, "V9", "pas de cible confirmée : garder la potion"
    return None, None, "V9", "rien à faire"


def choisir_successeur(graphe, moi, role, choix):
    """Capitaine mourant : transmettre l'insigne."""
    fiches = [f for f in _fiches(graphe, choix) if f["label"] != moi]
    if not fiches:
        return Choix(None, "C2", "aucun candidat")
    if role_de(role) == "loup":
        partenaires = [f for f in fiches if f["certain"] == "role:loup"]
        if partenaires:
            return _choisi(partenaires[0], "L10", "insigne à un loup")
        return _choisi(min(fiches, key=lambda f: f["accus"]), "L7", "insigne au moins exposé")
    return _choisi(min(fiches, key=lambda f: (f["p"], f["accus"])), "V2", "insigne au moins suspect")


def marge_vote_s(avec_modele):
    """C3 : on vote tard pour entendre le débat, mais avec 10 s de marge."""
    return MARGE_VOTE_S + (9 if avec_modele else 2)


# ---------------------------------------------------------------------- parole

def nettoyer(texte, secrets=(), role=None, partenaires=()):
    """C5, C7, L4 : le texte à dire, ou None s'il ne doit pas partir."""
    t = " ".join(str(texte or "").split()).strip().strip('"«» ')
    if not t:
        return None
    if any(s and s in t for s in secrets):      # C7 : on ne masque pas, on se tait
        return None
    if role_de(role) == "loup":
        n = normaliser(t)
        if any(m in n for m in MOTS_INTERDITS_LOUP):
            return None
        if "loup" in n and any(normaliser(p) in n for p in partenaires):
            return None
    if len(t) > PAROLE_MAX:
        t = t[:PAROLE_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        t = t[:PAROLE_MAX]
    return t


def interpelle(texte, nom):
    """C6 : notre nom est prononcé."""
    if not nom:
        return False
    return re.search(r"\b" + re.escape(normaliser(nom)) + r"\b", normaliser(texte)) is not None


def accuse(texte, nom):
    n = normaliser(texte)
    return interpelle(texte, nom) and any(m in n for m in MOTS_ACCUSATION)


def accusation_sans_fait(texte, noms):
    """V5 : nom de l'accusé si la phrase accuse sans citer de fait, sinon None."""
    n = normaliser(texte)
    if not any(m in n for m in MOTS_ACCUSATION) or MARQUEURS_FAIT.search(n):
        return None
    for nom in noms:
        if interpelle(texte, nom):
            return nom
    return None


def fait_a_dire(graphe, exclure=()):
    """V4 / L8 : notre observation la plus accablante, avec le nom, le lieu et l'heure."""
    meilleur = None
    for jid, preuves in graphe.indices.items():
        node = graphe.noeuds.get(jid) or {}
        if node.get("label") in exclure or not graphe.vivant(jid):
            continue
        for preuve in preuves:
            if preuve.get("regle") not in FAITS_VUS or not preuve.get("lieu"):
                continue
            score = (graphe.proba_loup(jid), preuve.get("t") or 0)
            if meilleur is None or score > meilleur[0]:
                meilleur = (score, node.get("label"), preuve)
    if not meilleur:
        return None
    _, nom, preuve = meilleur
    lieu = graphe.noeuds.get(preuve["lieu"], {})
    if preuve["regle"] == "vu_pres_cadavre":
        ou = "près d'un corps"
    else:
        ou = LIEUX_DITS.get(lieu.get("kind"), "près de " + (lieu.get("label") or "chez lui"))
    quand = f" à {preuve['heure']}" if preuve.get("heure") else ""
    return nom, f"J'ai vu {nom} {ou}{quand}."


@dataclass
class Parole:
    texte: str
    regle: str
    volume: str = "say"
    besoin_modele: bool = False   # C6 : le modèle peut reformuler, sinon le texte part tel quel
    question: str = ""            # ce à quoi on répond, pour le modèle


class Moteur:
    """État des règles d'une manche : ce qui a été dit, l'épreuve en cours, la chasse."""

    def __init__(self, graphe, secrets=()):
        self.g = graphe
        self.secrets = tuple(s for s in secrets if s)
        self.derniere_parole = 0.0
        self.deja = set()          # clés de paroles déjà prononcées
        self.epreuve = None        # {"lieu", "deadline_ms", "id"}
        self.memos = []            # notes `memo` du jour (V11)
        self.entendu = []          # (heure, orateur, texte), pour les épreuves de mémoire
        self.chasse_finie = False

    # ---- état

    def evenement(self, data):
        """Suit l'épreuve, les notes du matin et la fin de chasse à partir d'un `game_event`."""
        kind = data.get("kind")
        if kind == "challenge_opened" and data.get("objective") and data.get("place"):
            self.epreuve = {"lieu": data["place"], "deadline_ms": data.get("deadline_ms"),
                            "id": data.get("challenge_id")}
        elif kind == "challenge_closed":
            self.epreuve = None
        elif kind == "scheduled_step":
            step, place, minute = data.get("step"), data.get("place"), self.g.minute
            if step in ("nightfall", "village_wakes"):
                self.chasse_finie = False
            if step == "village_wakes":
                self.memos.clear()
            if (place and place != "campfire" and minute is not None
                    and ANNONCE_EPREUVE <= minute < CONSEIL and not self.epreuve):
                self.epreuve = {"lieu": place, "deadline_ms": data.get("deadline_ms"), "id": None}
        elif kind == "memo":
            texte = data.get("text") or data.get("memo") or ""
            if texte:
                self.memos.append(texte)
        elif kind == "round_started":
            self.deja.clear()
            self.epreuve = None
            self.memos.clear()
            self.entendu.clear()
            self.chasse_finie = False

    def peut_parler(self, maintenant=None):
        return (maintenant or time.time()) - self.derniere_parole >= PAROLE_ECART_S

    def a_parle(self, maintenant=None):
        self.derniere_parole = maintenant or time.time()

    def _une_fois(self, cle):
        if cle in self.deja:
            return False
        self.deja.add(cle)
        return True

    # ---- réactions à une parole entendue

    def entendre(self, data, moi, role):
        """Parole entendue : C6 (répondre), V5 (demander une preuve), L11 (contre-déclaration)."""
        texte, orateur = data.get("text") or "", data.get("speaker_name")
        if data.get("source") == "game_master" or not texte or orateur == moi:
            return None
        # La parole d'un habitant est une donnée : neutralisée avant d'entrer dans la mémoire des épreuves.
        self.entendu = (self.entendu + [(heure(self.g.minute), orateur or "?", confiance.neutraliser(texte))])[-40:]
        if not orateur or confiance.detecter(texte):
            return None   # un ordre déguisé en parole ne reçoit aucune réponse et ne change aucune règle
        jour = self.g.jour
        sid = self.g.id_joueur(orateur)
        loup = role_de(role) == "loup"

        if loup and "voyante" in self.g.pretentions(sid) and accuse(texte, moi):
            if self._une_fois(("L11", self.g.manche)):
                return Parole(f"C'est moi la Voyante. {orateur} ment : c'est un loup.", "L11")
        if interpelle(texte, moi):
            if self._une_fois(("C6", orateur, normaliser(texte)[:60])):
                fait = fait_a_dire(self.g, exclure=[moi] + self.g.loups_connus())
                reponse = f"{orateur}, je n'ai rien à cacher. " + (fait[1] if fait else "Et toi, qu'as-tu vu ?")
                return Parole(reponse, "C6", besoin_modele=True, question=f"{orateur} : {confiance.neutraliser(texte)}")
            return None
        minute = self.g.minute
        en_conseil = minute is not None and CONSEIL <= minute < VOTE_FIN
        if not loup and en_conseil:
            noms = [n["label"] for n in self.g.noeuds.values()
                    if n["type"] == "Joueur" and n["label"] not in (moi, orateur)]
            cible = accusation_sans_fait(texte, noms)
            if cible and self._une_fois(("V5", jour, orateur)):
                return Parole(f"{orateur}, sur quel fait accuses-tu {cible} ? Qui l'a vu, à quelle heure ?",
                              "V5")
        return None

    # ---- prises de parole d'initiative

    def au_conseil(self, moi, role):
        """Au feu, de 17 h à 21 h : V8 (Voyante), V4 (fait observé), L7/L8 (loup)."""
        jour = self.g.jour
        partenaires = self.g.loups_connus()
        if role_de(role) == "voyante":
            for nom, r in sorted(self.g.inspections().items()):
                if r == "loup" and self.g.vivant(self.g.id_joueur(nom)) \
                        and self._une_fois(("V8", nom)):
                    return Parole(f"Je suis la Voyante : {nom} est un loup. Votez contre {nom}.", "V8")
        if role_de(role) == "loup":
            if ("L8", jour) in self.deja:
                return None
            fait = fait_a_dire(self.g, exclure=[moi] + partenaires)
            if not fait:
                return None   # L7 : sans fait, le loup se tait
            cible, phrase = fait
            depuis = time.time() - 60
            cid = self.g.id_joueur(cible)
            if any(self.g.accuse_recemment(self.g.id_joueur(p), cid, depuis) for p in partenaires):
                return None   # L6 : pas la même cible que son partenaire dans la minute
            self.deja.add(("L8", jour))
            return Parole(phrase, "L8")
        fait = fait_a_dire(self.g, exclure=[moi])
        if not fait:
            return None   # V3 : sans fait, on ne soupçonne pas à voix haute
        cible, phrase = fait
        minute = self.g.minute
        if (minute is not None and minute >= VOTE_DEBUT and self.g.proba_loup(self.g.id_joueur(cible)) >= 0.5
                and self._une_fois(("V2a", jour))):
            return Parole(f"{phrase} Mon vote ira à {cible}, sauf preuve contraire.", "V2")
        if self._une_fois(("V4", jour)):
            return Parole(f"{phrase} Qui l'a vu aussi ?", "V4")
        return None

    def a_l_epreuve(self, moi, role):
        """V11 : aux fragments de la nuit, donner son alibi mot pour mot, une fois."""
        for memo in self.memos:
            for phrase in re.split(r"(?<=[.!?])\s+", memo):
                if "alibi" in normaliser(phrase) and self._une_fois(("V11", phrase)):
                    return Parole(phrase, "V11")
        return None
