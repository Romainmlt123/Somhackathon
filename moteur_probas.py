"""Moteur de probabilités des décisions : pour une situation, note chaque option possible et
renvoie une distribution de probabilités, sans appel au modèle.

Principe :
- chaque option reçoit une utilité entre 0 et 1, calculée à partir du graphe (p(loup) de chaque
  joueur, rôles certains, Capitaine) et des règles du livret (points, potions, horaires) ;
- un softmax à température transforme les utilités en probabilités ;
- `confiance` = écart entre les deux meilleures options. Sous `SEUIL_MODELE`, la situation est
  ambiguë : le moteur de décision peut alors consulter le modèle (prix de Sobriété oblige).

Usage :
    from moteur_probas import Contexte, evaluer
    ctx = Contexte.depuis_graphe(self.graphe, mon_role="villageois")
    res = evaluer(ctx, decision_request)       # invitation reçue du serveur
    res.meilleure, res.probas, res.confiance, res.consulter_modele
    evaluer_agenda(ctx)                         # que faire maintenant, hors invitation

Voir DECISIONS.md pour la carte complète des décisions.
"""
import math
from dataclasses import dataclass, field

TEMPERATURE = 0.15     # plus bas = plus tranché
SEUIL_MODELE = 0.15    # écart de probabilité sous lequel on consulte le modèle
SEUIL_POISON = 0.80    # p(loup) minimale pour utiliser la potion de mort
SEUIL_ACCUSER = 0.70   # p(loup) minimale pour accuser à voix haute

LOUP, VILLAGEOIS, VOYANTE, SORCIERE = "loup", "villageois", "voyante", "sorciere"


def _norme_role(role):
    r = (role or "").lower()
    for nom, cle in (("loup", LOUP), ("wolf", LOUP), ("voyant", VOYANTE), ("seer", VOYANTE),
                     ("sorci", SORCIERE), ("witch", SORCIERE)):
        if nom in r:
            return cle
    return VILLAGEOIS


@dataclass
class Contexte:
    """Ce que le moteur sait. `p_loup` : nom → probabilité d'être loup (1.0 / 0.0 si certain)."""
    mon_nom: str = ""
    mon_role: str = VILLAGEOIS
    p_loup: dict = field(default_factory=dict)
    roles_certains: dict = field(default_factory=dict)   # nom → rôle révélé
    vivants: set = field(default_factory=set)
    capitaine: str | None = None
    allies_loups: set = field(default_factory=set)       # connus si je suis loup
    minute: int | None = None                            # minute du jour (0-1439)
    jour: int | None = None
    potion_vie: bool = True
    potion_mort: bool = True
    inspections_restantes: int = 2

    @classmethod
    def depuis_graphe(cls, graphe, mon_role=None, **kw):
        joueurs = [n for n in graphe.noeuds.values() if n["type"] == "Joueur"]
        moi = graphe.noeuds.get(graphe.moi, {}).get("label", "")
        p = {n["label"]: graphe.proba_loup(n["id"]) for n in joueurs if n["id"] != graphe.moi}
        certains = {graphe.noeuds[j]["label"]: r.split(":", 1)[1] for j, r in graphe.certain.items()
                    if j in graphe.noeuds}
        vivants = {n["label"] for n in joueurs if n.get("vivant") is not False}
        role = _norme_role(mon_role or graphe.noeuds.get(graphe.moi, {}).get("role"))
        allies = {nom for nom, r in certains.items() if _norme_role(r) == LOUP} if role == LOUP else set()
        return cls(mon_nom=moi, mon_role=role, p_loup=p, roles_certains=certains, vivants=vivants,
                   allies_loups=allies, minute=graphe.minute, jour=graphe.jour, **kw)

    def p(self, nom):
        if nom in self.allies_loups:
            return 1.0
        return self.p_loup.get(nom, 0.25)


@dataclass
class Resultat:
    kind: str
    action: str
    utilites: dict          # choice_id → utilité
    probas: dict            # choice_id → probabilité
    raisons: dict           # choice_id → explication courte
    meilleure: str | None
    confiance: float
    consulter_modele: bool

    def pour_journal(self):
        """Champs prêts pour journal.why(...)."""
        return {"kind": self.kind, "choix": self.meilleure, "confiance": round(self.confiance, 3),
                "probas": {k: round(v, 3) for k, v in self.probas.items()},
                "raisons": self.raisons, "consulter_modele": self.consulter_modele}


def softmax(utilites, temperature=TEMPERATURE):
    if not utilites:
        return {}
    m = max(utilites.values())
    e = {k: math.exp((u - m) / temperature) for k, u in utilites.items()}
    s = sum(e.values())
    return {k: v / s for k, v in e.items()}


def _resultat(kind, action, notes):
    """notes : choice_id → (utilité, raison)."""
    utilites = {k: max(0.0, min(1.0, u)) for k, (u, _) in notes.items()}
    probas = softmax(utilites)
    rang = sorted(probas.values(), reverse=True) + [0.0]
    meilleure = max(probas, key=probas.get) if probas else None
    confiance = rang[0] - rang[1]
    return Resultat(kind, action, utilites, probas, {k: r for k, (_, r) in notes.items()},
                    meilleure, confiance, confiance < SEUIL_MODELE and len(probas) > 1)


# ------------------------------------------------------------------ une note par type de décision

def _vote_conseil(ctx, choix):
    """Village : +1 point par vote contre un loup → voter pour le p(loup) max.
    Loup : faire éliminer le villageois le plus soupçonné (vote crédible), jamais un allié."""
    notes = {}
    for cid, nom in choix.items():
        p = ctx.p(nom)
        if nom == ctx.mon_nom:
            notes[cid] = (0.0, "soi-même")
        elif ctx.mon_role == LOUP:
            if nom in ctx.allies_loups:
                notes[cid] = (0.0, "allié loup")
            else:   # on suit les soupçons du village : p vue du village ≈ p_loup du graphe
                notes[cid] = (0.3 + 0.7 * p, f"innocent soupçonné par le village (p={p:.2f})")
        else:
            notes[cid] = (p, f"p(loup)={p:.2f}")
    return notes


def _election_capitaine(ctx, choix):
    notes = {}
    for cid, nom in choix.items():
        if nom == ctx.mon_nom:
            notes[cid] = (0.9 if ctx.mon_role == LOUP else 0.6, "moi : voix décisive aux égalités")
        elif ctx.mon_role == LOUP:
            notes[cid] = (0.8 if nom in ctx.allies_loups else 0.2, "allié" if nom in ctx.allies_loups else "autre")
        else:
            notes[cid] = (1 - ctx.p(nom), f"confiance={1 - ctx.p(nom):.2f}")
    return notes


def _inspection(ctx, choix):
    """Voyante : inspecter là où l'incertitude est maximale (entropie), Capitaine en bonus."""
    notes = {}
    for cid, nom in choix.items():
        if nom in ctx.roles_certains or nom == ctx.mon_nom:
            notes[cid] = (0.0, "rôle déjà connu")
            continue
        p = min(max(ctx.p(nom), 1e-6), 1 - 1e-6)
        h = -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
        bonus = 0.15 if nom == ctx.capitaine else 0.0
        notes[cid] = (h * 0.85 + bonus, f"incertitude={h:.2f}" + (", Capitaine" if bonus else ""))
    return notes


def _potion(ctx, actions):
    """Sorcière : actions = {nom_action: {choice_id: nom}}. Renvoie des options 'action:choice_id'."""
    notes = {"abstain": (0.35, "garder les potions")}
    for cid, nom in actions.get("heal", {}).items():
        if ctx.potion_vie:
            p = ctx.p(nom)
            bonus = 0.2 if nom in (ctx.mon_nom, ctx.capitaine) or _norme_role(ctx.roles_certains.get(nom)) == VOYANTE else 0
            notes[f"heal:{cid}"] = (0.9 - 0.8 * p + bonus, f"sauver {nom} (p={p:.2f})")
    for cid, nom in actions.get("poison", {}).items():
        p = ctx.p(nom)
        if ctx.potion_mort and nom != ctx.mon_nom:
            u = 0.9 * p if p >= SEUIL_POISON else 0.1 * p
            notes[f"poison:{cid}"] = (u, f"empoisonner {nom} (p={p:.2f})")
    return notes


def _succession(ctx, choix):
    notes = {}
    for cid, nom in choix.items():
        if ctx.mon_role == LOUP:
            notes[cid] = (0.9 if nom in ctx.allies_loups else 0.1, "allié" if nom in ctx.allies_loups else "autre")
        else:
            notes[cid] = (1 - ctx.p(nom), f"confiance={1 - ctx.p(nom):.2f}")
    return notes


def cibles_attaque(ctx, visibles, menaces=()):
    """Loup : noter les cibles visibles à 2 m. `menaces` : noms qui m'ont accusé."""
    notes = {}
    for nom in visibles:
        if nom in ctx.allies_loups or nom == ctx.mon_nom:
            continue
        r = _norme_role(ctx.roles_certains.get(nom))
        u = 0.4
        u += 0.35 if r in (VOYANTE, SORCIERE) else 0
        u += 0.2 if nom == ctx.capitaine else 0
        u += 0.25 if nom in menaces else 0
        u -= 0.2 * ctx.p(nom)      # un suspect sera éliminé au conseil de toute façon
        notes[nom] = (u, f"rôle={r}, capitaine={nom == ctx.capitaine}, menace={nom in menaces}")
    return _resultat("attack", "attack", notes)


# ------------------------------------------------------------------ points d'entrée

_PAR_KIND = {"council_vote": _vote_conseil, "captain_election": _election_capitaine,
             "seer_inspect": _inspection, "captain_succession": _succession}


def evaluer(ctx, request):
    """Évalue une `decision_request` (champ data). Renvoie un Resultat, ou None si c'est une
    épreuve (challenge_answer) : elle relève du modèle."""
    kind = request.get("kind")
    actions = {a["action"]: {c["choice_id"]: c["label"] for c in a.get("choices", [])}
               for a in request.get("actions", [])}
    if kind == "witch_self_rescue":
        cid = next(iter(actions.get("heal", {})), None)
        return _resultat(kind, "heal", {cid or "heal": (1.0, "se sauver soi-même")})
    if kind == "witch_potion":
        return _resultat(kind, "potion", _potion(ctx, actions))
    if kind in _PAR_KIND:
        action, choix = next(iter(actions.items()), (None, {}))
        notes = _PAR_KIND[kind](ctx, choix)
        if request.get("allow_abstain"):
            notes["abstain"] = (0.05, "abstention")
        return _resultat(kind, action, notes)
    return None


def evaluer_agenda(ctx, en_epreuve=False, epreuve_ia=False):
    """Que faire maintenant, hors invitation : options pondérées selon l'heure et le rôle."""
    m = ctx.minute if ctx.minute is not None else 720
    h = m / 60
    nuit = h >= 22 or h < 8
    notes = {}
    if nuit:
        if ctx.mon_role == LOUP and (h >= 22 or h < 6):
            notes["chasser"] = (0.8, "22 h-6 h : transform à la pierre puis attack")
            notes["dormir"] = (0.3, "éviter la fatigue")
        else:
            notes["dormir"] = (0.9, "nuit : rentrer et dormir 7 h (sinon fatigue)")
            if ctx.mon_role == VOYANTE and ctx.inspections_restantes:
                notes["inspecter"] = (0.95, "depuis sa maison, 22 h-8 h")
    else:
        notes["explorer"] = (0.35, "cartographier, observer")
        notes["ecouter"] = (0.4, "se poster près des autres pour entendre")
        if 8.5 <= h < 9 + 2 and ctx.jour in (None, 1):
            notes["aller_conseil"] = (0.7, "élection du Capitaine 9 h-11 h le premier jour")
        if 14 <= h < 15.5 and epreuve_ia:
            notes["aller_epreuve"] = (0.85, "épreuve IA à 15 h : être présent à la clôture")
        if en_epreuve:
            notes["rester_epreuve"] = (0.9, "présence à la clôture = points")
        if 17 <= h < 21:
            notes["aller_conseil"] = (0.9, "conseil 17 h, vote 19 h-21 h au feu")
        suspect = max(ctx.p_loup, key=ctx.p_loup.get, default=None)
        if suspect and ctx.p(suspect) >= SEUIL_ACCUSER and ctx.mon_role != LOUP:
            notes["accuser"] = (0.6, f"accuser {suspect} (p={ctx.p(suspect):.2f})")
        if h >= 21.5:
            notes["rentrer"] = (0.8, "la nuit approche : return_home")
    return _resultat("agenda", "agenda", notes)


if __name__ == "__main__":
    ctx = Contexte(mon_nom="Moi", mon_role=VILLAGEOIS, p_loup={"Léa": 0.72, "Émile": 0.31, "Zoé": 0.18},
                   minute=19 * 60 + 10)
    req = {"kind": "council_vote", "allow_abstain": False, "actions": [{"action": "vote", "format": "choice",
           "choices": [{"choice_id": "v1", "label": "Léa"}, {"choice_id": "v2", "label": "Émile"},
                       {"choice_id": "v3", "label": "Zoé"}]}]}
    print(evaluer(ctx, req).pour_journal())
    print(evaluer_agenda(ctx).pour_journal())
