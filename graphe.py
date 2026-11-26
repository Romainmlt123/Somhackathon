"""Graphe de connaissances construit à partir du journal de l'agent (`journal.py`).

Nœuds : `Joueur`, `Lieu`, `Role`, `Silhouette` (loup transformé, anonyme).
Arêtes, chacune avec un poids entre 0 et 1 et la liste des preuves (`n` des lignes du journal) :

| Relation         | De → vers          | Poids                                               |
|------------------|--------------------|-----------------------------------------------------|
| `HABITE`         | Joueur → Lieu      | 1 pour soi (`self.home`), sinon croît avec les indices |
| `EST_MORT_A`     | Joueur → Lieu      | 1 au conseil, moins quand le lieu est déduit d'un cadavre |
| `A_LE_ROLE`      | Joueur → Role      | 1 : rôle certain (le sien, révélé, inspecté)         |
| `SOUPCONNE_ETRE` | Joueur → Role loup | probabilité d'être loup, mise à jour par indices      |
| `PRETEND_ETRE`   | Joueur → Role      | le joueur a dit avoir ce rôle                         |
| `VU_PRES_DE`     | Joueur → Lieu      | croît avec le nombre d'observations                   |
| `ACCUSE`         | Joueur → Joueur    | croît avec le nombre d'accusations entendues          |
| `A_VOTE_CONTRE`  | Joueur → Joueur    | nos propres votes                                     |

Le graphe ne dépend que du journal : `Graphe.depuis_jsonl(chemin)` le recalcule après coup,
ce qui permet d'ajuster les règles et les poids (`POIDS`) sans rejouer la manche.

Les formes exactes des `game_event` `vote_closed` et `dawn` ne sont pas détaillées par le
protocole : leurs extracteurs essaient plusieurs clés et le message brut reste dans le journal.
"""

import json
import math
import re
import time
import unicodedata
from pathlib import Path

# Lieux nommés du village. Les lits, bancs et portes sont trop nombreux pour être des nœuds.
REPERES = {"house", "chapel", "canteen", "campfire", "board", "stone"}
LIEU_CONSEIL = "lieu:campfire"

PRIOR_LOUP = 0.25  # « environ un habitant sur quatre est loup »

# Variation de log-cote de « est loup » pour chaque indice. À ajuster après les manches.
POIDS = {
    "vu_pres_pierre_nuit": 1.0,     # les loups se transforment à la pierre, 22 h-6 h
    "vu_pres_cadavre": 0.7,
    "debout_dehors_nuit": 0.3,      # un villageois a intérêt à dormir
    "accuse_par_autrui": 0.2,
    "cite_par_indice": 0.9,         # l'Indice nomme trois vivants dont au moins un loup
    "a_accuse_un_loup": -0.6,       # révélé ensuite comme loup
    "a_accuse_un_innocent": 0.3,    # révélé ensuite comme villageois
    "accusation_en_miroir": 0.5,    # V6 : même cible, mêmes mots qu'un autre, dans la minute
}
SEUIL_MIROIR = 0.5   # part de mots communs (Jaccard) au-delà de laquelle deux accusations se copient

ROLES_ALIAS = {
    "loup": "loup", "loups": "loup", "wolf": "loup", "werewolf": "loup", "loup-garou": "loup",
    "voyante": "voyante", "seer": "voyante",
    "sorciere": "sorciere", "witch": "sorciere",
    "villageois": "villageois", "villager": "villageois",
}
MOTS_ACCUSATION = ("loup", "suspect", "menteur", "menteuse", "accuse", "vote contre",
                   "votez contre", "eliminez", "coupable")
MAX_PREUVES = 20


def _sans_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    ).lower()


def _role_id(role):
    role = str(role)
    return "role:" + ROLES_ALIAS.get(_sans_accents(role), _sans_accents(role))


def _logit(p):
    return math.log(p / (1 - p))


def _sigmoid(x):
    return 1 / (1 + math.exp(-x))


def _ecart(a, b):
    """Distance entre deux objets vus au même instant, à partir de leurs (distance, angle)."""
    da, db = a.get("distance_m"), b.get("distance_m")
    if da is None or db is None:
        return None
    angle = math.radians((a.get("bearing_deg", 0) - b.get("bearing_deg", 0)))
    return math.sqrt(max(0.0, da * da + db * db - 2 * da * db * math.cos(angle)))


def _nom(value):
    """Un nom de joueur dans un champ qui peut être une chaîne ou un objet."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("name", "label", "player", "villager"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def _role_de(value):
    if isinstance(value, dict):
        for key in ("role", "revealed_role", "role_revealed"):
            if value.get(key):
                return value[key]
    return None


class Graphe:
    def __init__(self):
        self.noeuds = {}
        self.aretes = {}
        self.archives = []          # arêtes des manches précédentes
        self.moi = None
        self.manche = None
        self._minute = self._minute_t = self._cycle_ms = None
        self.extrapoler = False     # vrai en direct : l'heure avance entre deux messages du serveur
        self.jour = self.minute = None
        self.refs = {}              # ref de perception → id de nœud
        self.visibles = {}          # ref → dernière observation
        self.repere_de = {}         # ref de personne → lieu le plus proche, au dernier calcul
        self.invitations = {}       # request_id → {choice_id: label}
        self.commandes = {}         # command_id → data envoyée
        self.cadavres = []          # cadavres vus : {t, n, jour, lieu, nom}
        self.logcote = {}           # joueur id → log-cote d'être loup
        self.indices = {}           # joueur id → preuves de soupçon
        self.certain = {}           # joueur id → rôle certain
        self.paroles = []           # dernières paroles, relues quand un nouveau joueur apparaît
        self.accusations = []       # (orateur, cible, mots, t), pour repérer les miroirs (V6)
        self.miroirs = set()        # paires d'orateurs déjà signalées
        self.potions_utilisees = set()   # "heal" / "poison" acceptés par le serveur, cette manche
        self.nb_inspections = 0          # inspections de Voyante acceptées, cette manche

    # ------------------------------------------------------------------ construction

    @classmethod
    def depuis_jsonl(cls, chemin):
        graphe = cls()
        with open(chemin, encoding="utf-8") as fichier:
            for ligne in fichier:
                if ligne.strip():
                    graphe.observe(json.loads(ligne))
        return graphe

    def noeud(self, id_, type_, label, **props):
        node = self.noeuds.setdefault(id_, {"id": id_, "type": type_, "label": label})
        node.update({k: v for k, v in props.items() if v is not None})
        return id_

    def joueur(self, nom, **props):
        id_ = "joueur:" + nom
        nouveau = id_ not in self.noeuds
        self.noeud(id_, "Joueur", nom, **props)
        if nouveau:
            # Une accusation entendue avant de connaître ce nom compte aussi.
            for orateur, texte, rec in self.paroles:
                self._accusation(orateur, texte, rec, [self.noeuds[id_]])
        return id_

    def lieu(self, obs):
        nom = obs.get("name") or obs["kind"]
        return self.noeud("lieu:" + nom, "Lieu", nom, kind=obs["kind"])

    def role(self, role):
        id_ = _role_id(role)
        return self.noeud(id_, "Role", id_.split(":", 1)[1])

    def arete(self, src, rel, dst, rec, regle, poids=None, increment=None, **props):
        """Ajoute une preuve à une arête. `poids` fixe le poids, `increment(nb)` le calcule."""
        key = (src, rel, dst)
        edge = self.aretes.get(key)
        if edge is None:
            edge = self.aretes[key] = {
                "src": src, "rel": rel, "dst": dst, "weight": 0.0, "count": 0,
                "first_t": rec.get("t"), "manche": self.manche, "preuves": [],
            }
        edge["count"] += 1
        edge["last_t"] = rec.get("t")
        if poids is not None:
            edge["weight"] = round(max(edge["weight"], poids), 3)
        elif increment is not None:
            edge["weight"] = round(increment(edge["count"]), 3)
        edge.update(props)
        edge["preuves"] = (edge["preuves"] + [self._preuve(rec, regle)])[-MAX_PREUVES:]
        return edge

    def _preuve(self, rec, regle, **extra):
        preuve = {"n": rec.get("n"), "t": rec.get("t"), "regle": regle}
        if self.jour is not None:
            preuve["jour"] = self.jour
        if self.minute is not None:
            preuve["heure"] = f"{self.minute // 60:02d}:{self.minute % 60:02d}"
        preuve.update(extra)
        return preuve

    # ------------------------------------------------------------------ soupçons

    def soupcon(self, joueur_id, regle, rec, **extra):
        if joueur_id == self.moi or joueur_id in self.certain:
            return
        delta = POIDS[regle]
        self.logcote[joueur_id] = self.logcote.get(joueur_id, _logit(PRIOR_LOUP)) + delta
        preuves = self.indices.setdefault(joueur_id, [])
        preuves.append(self._preuve(rec, regle, delta=delta, **extra))
        del preuves[:-MAX_PREUVES]

    def proba_loup(self, joueur_id):
        if joueur_id in self.certain:
            return 1.0 if self.certain[joueur_id] == "role:loup" else 0.0
        return _sigmoid(self.logcote.get(joueur_id, _logit(PRIOR_LOUP)))

    def fixe_role(self, joueur_id, role, rec, regle):
        role_id = self.role(role)
        self.certain[joueur_id] = role_id
        self.arete(joueur_id, "A_LE_ROLE", role_id, rec, regle, poids=1.0)
        # Ce qu'un joueur a dit d'un loup révélé renseigne sur lui-même.
        for (src, rel, dst), edge in list(self.aretes.items()):
            if rel == "ACCUSE" and dst == joueur_id:
                self.soupcon(
                    src,
                    "a_accuse_un_loup" if role_id == "role:loup" else "a_accuse_un_innocent",
                    rec,
                    cible=joueur_id,
                )

    # ------------------------------------------------------------------ horloge

    @property
    def minute(self):
        """Minute du village. En direct, elle avance seule entre deux messages (`cycle_ms`)."""
        if self._minute is None or not (self.extrapoler and self._cycle_ms):
            return self._minute
        ecoule_ms = (time.time() - self._minute_t) * 1000
        return int(self._minute + ecoule_ms * 1440 / self._cycle_ms) % 1440

    @minute.setter
    def minute(self, valeur):
        self._minute, self._minute_t = valeur, time.time()

    def nuit(self):
        return self.minute is not None and (self.minute >= 1320 or self.minute < 480)

    def heure_des_loups(self):
        return self.minute is not None and (self.minute >= 1320 or self.minute < 360)

    def _horloge(self, clock):
        if isinstance(clock, dict):
            self.jour = clock.get("day", self.jour)
            if clock.get("minute") is not None:
                self.minute = clock["minute"]
            self._cycle_ms = clock.get("cycle_ms", self._cycle_ms)

    # ------------------------------------------------------------------ lecture du journal

    def observe(self, rec):
        ev = rec.get("ev")
        if ev == "in":
            handler = getattr(self, "_in_" + str(rec.get("type")), None)
            if handler and isinstance(rec.get("data"), dict):
                handler(rec["data"], rec)
        elif ev == "out":
            self._out(rec)

    def _out(self, rec):
        data = rec.get("data") or {}
        if rec.get("type") != "act" or not rec.get("command_id"):
            return
        self.commandes[rec["command_id"]] = data
        if data.get("action") == "vote" and self.moi:
            label = self.invitations.get(data.get("request_id"), {}).get(data.get("choice_id"))
            if label:
                self.arete(self.moi, "A_VOTE_CONTRE", self.joueur(label), rec, "notre vote",
                           poids=1.0)

    def _in_snapshot(self, data, rec):
        if data.get("status") == "dead" and self.moi:
            self.noeuds[self.moi]["vivant"] = False
        # La manche d'abord : en changer archive les rôles, dont celui de `self`.
        if isinstance(data.get("round"), dict):
            self._nouvelle_manche(data["round"].get("round_id"))
        self._horloge(data.get("clock"))
        if data.get("self"):
            self._in_self(data["self"], rec)
        self.visibles.clear()
        self.repere_de.clear()
        if "visible" in data:
            self._in_vision({"entered": data.get("visible") or [], "updated": [], "left": []},
                            rec)
        for req in data.get("requests") or []:
            self._in_decision_request(req, rec)

    def _in_self(self, data, rec):
        if not data.get("name"):
            return
        self.moi = self.joueur(data["name"], moi=True, vivant=True,
                               capitaine=data.get("captain"))
        if data.get("role"):
            self.fixe_role(self.moi, data["role"], rec, "self.role")
        if data.get("home"):
            maison = self.noeud("lieu:" + data["home"], "Lieu", data["home"], kind="house")
            self.arete(self.moi, "HABITE", maison, rec, "self.home", poids=1.0)

    def _in_vision(self, data, rec):
        for ref in data.get("left") or []:
            self.visibles.pop(ref, None)
            self.repere_de.pop(ref, None)
        nouveaux = data.get("entered") or []
        for obs in nouveaux + (data.get("updated") or []):
            if obs.get("ref"):
                self.visibles[obs["ref"]] = obs
        # Les repères d'abord : une personne se situe par rapport à eux.
        for obs in nouveaux + (data.get("updated") or []):
            if obs.get("kind") in REPERES:
                self.refs[obs["ref"]] = self.lieu(obs)
        for obs in nouveaux + (data.get("updated") or []):
            kind = obs.get("kind")
            if kind == "person":
                self._personne(obs, rec)
            elif kind == "wolf":
                self._loup(obs, rec)
            elif kind == "corpse":
                self._cadavre(obs, rec)

    def _repere_proche(self, obs, max_m=15.0):
        meilleur = None
        for ref, other in self.visibles.items():
            if other.get("kind") in REPERES and ref != obs.get("ref"):
                d = _ecart(obs, other)
                if d is not None and d <= max_m and (meilleur is None or d < meilleur[1]):
                    meilleur = (self.refs.get(ref) or self.lieu(other), d)
        return meilleur

    def _personne(self, obs, rec):
        if not obs.get("name"):
            return
        jid = self.joueur(obs["name"], engaged=obs.get("engaged"), posture=obs.get("posture"))
        self.refs[obs["ref"]] = jid
        proche = self._repere_proche(obs)
        lieu = proche[0] if proche else None
        if lieu is None or self.repere_de.get(obs["ref"]) == lieu:
            return  # on n'ajoute une preuve que quand le repère le plus proche change
        self.repere_de[obs["ref"]] = lieu
        self.arete(jid, "VU_PRES_DE", lieu, rec, "vision",
                   increment=lambda k: 1 - math.exp(-k / 3), distance_m=round(proche[1], 1))
        kind = self.noeuds[lieu].get("kind")
        if kind == "stone" and self.heure_des_loups() and proche[1] <= 6:
            self.soupcon(jid, "vu_pres_pierre_nuit", rec, lieu=lieu)
        if self.nuit() and kind == "house":
            # Vu près d'une maison la nuit : indice faible de domicile.
            self.arete(jid, "HABITE", lieu, rec, "vu près de la maison la nuit",
                       increment=lambda k: min(0.9, 0.25 * k))
        if self.nuit() and obs.get("posture") not in ("sleeping", "lying") and kind != "house":
            self.soupcon(jid, "debout_dehors_nuit", rec, lieu=lieu)
        for cadavre in self.cadavres[-5:]:
            if cadavre["lieu"] == lieu and rec.get("t", 0) - cadavre["t"] < 120:
                self.soupcon(jid, "vu_pres_cadavre", rec, lieu=lieu)
                break

    def _loup(self, obs, rec):
        if obs.get("name"):  # seul un loup voit le nom d'un autre loup
            jid = self.joueur(obs["name"])
            self.refs[obs["ref"]] = jid
            if self.certain.get(jid) != "role:loup":
                self.fixe_role(jid, "loup", rec, "loup nommé en vue")
            return
        sid = self.noeud("silhouette:" + obs["ref"], "Silhouette", "loup anonyme")
        self.refs[obs["ref"]] = sid
        self.arete(sid, "A_LE_ROLE", self.role("loup"), rec, "loup transformé", poids=1.0)
        proche = self._repere_proche(obs)
        if proche:
            self.arete(sid, "VU_PRES_DE", proche[0], rec, "vision",
                       increment=lambda k: 1 - math.exp(-k / 3))

    def _cadavre(self, obs, rec):
        proche = self._repere_proche(obs)
        if not proche:
            return
        lieu = proche[0]
        if any(c["lieu"] == lieu and c.get("ref") == obs.get("ref") for c in self.cadavres):
            return
        self.cadavres.append({"t": rec.get("t"), "n": rec.get("n"), "jour": self.jour,
                              "lieu": lieu, "ref": obs.get("ref"), "nom": obs.get("name")})
        if obs.get("name"):
            jid = self.joueur(obs["name"], vivant=False)
            self.arete(jid, "EST_MORT_A", lieu, rec, "cadavre reconnu", poids=0.9)
        # Les vivants déjà en vue près du corps.
        for ref, other in self.visibles.items():
            if other.get("kind") == "person" and other.get("name"):
                d = _ecart(obs, other)
                if d is not None and d <= 5:
                    self.soupcon(self.joueur(other["name"]), "vu_pres_cadavre", rec, lieu=lieu)

    def _in_sound(self, data, rec):
        if data.get("kind") != "speech" or not data.get("text"):
            return
        orateur = data.get("speaker_name")
        if not orateur:
            return
        sid = self.joueur(orateur)
        texte = _sans_accents(data["text"])
        for role_brut, role in ROLES_ALIAS.items():
            if re.search(r"\bje suis (la |le |un |une )?" + re.escape(role_brut) + r"\b", texte):
                self.arete(sid, "PRETEND_ETRE", self.role(role), rec, "déclaration",
                           poids=0.5, texte=data["text"][:240])
                break
        if not any(mot in texte for mot in MOTS_ACCUSATION):
            return
        self.paroles = (self.paroles + [(sid, data["text"], rec)])[-50:]
        self._accusation(sid, data["text"], rec, list(self.noeuds.values()))

    def _accusation(self, sid, brut, rec, candidats):
        texte = _sans_accents(brut)
        for node in candidats:
            if node["type"] != "Joueur" or node["id"] == sid:
                continue
            if re.search(r"\b" + re.escape(_sans_accents(node["label"])) + r"\b", texte):
                self.arete(sid, "ACCUSE", node["id"], rec, "parole",
                           increment=lambda k: 1 - math.exp(-k / 2), texte=brut[:240])
                self.soupcon(node["id"], "accuse_par_autrui", rec, par=sid)
                self._miroir(sid, node, texte, rec)

    def _miroir(self, sid, cible, texte, rec):
        """V6 : deux joueurs accusent la même cible avec les mêmes mots, à moins d'une minute."""
        mots = set(re.findall(r"[a-z]{4,}", texte)) - set(
            re.findall(r"[a-z]+", _sans_accents(cible["label"])))
        t = rec.get("t") or 0
        for autre, cible_id, mots_autre, t_autre in self.accusations:
            if autre == sid or cible_id != cible["id"] or abs(t - t_autre) > 60:
                continue
            if mots and mots_autre and len(mots & mots_autre) / len(mots | mots_autre) >= SEUIL_MIROIR:
                paire = tuple(sorted((autre, sid)))
                if paire not in self.miroirs:
                    self.miroirs.add(paire)
                    self.soupcon(sid, "accusation_en_miroir", rec, avec=autre, cible=cible["id"])
                    self.soupcon(autre, "accusation_en_miroir", rec, avec=sid, cible=cible["id"])
        self.accusations = (self.accusations + [(sid, cible["id"], mots, t)])[-30:]

    def _in_decision_request(self, data, rec):
        choix = {}
        for action in data.get("actions") or []:
            for c in action.get("choices") or []:
                choix[c.get("choice_id")] = c.get("label")
                if data.get("kind") in ("council_vote", "captain_election", "seer_inspect",
                                        "witch_potion") and c.get("label"):
                    self.joueur(c["label"])
        if data.get("request_id"):
            self.invitations[data["request_id"]] = choix

    def _in_command_result(self, data, rec):
        envoi = self.commandes.pop(data.get("command_id"), None)
        if not envoi or not data.get("ok"):
            return
        valeur = data.get("value") or {}
        if envoi.get("action") in ("heal", "poison"):
            self.potions_utilisees.add(envoi["action"])
        if envoi.get("action") == "inspect":
            self.nb_inspections += 1
        if envoi.get("action") == "inspect" and valeur.get("role"):
            label = self.invitations.get(envoi.get("request_id"), {}).get(envoi.get("choice_id"))
            if label:
                self.fixe_role(self.joueur(label), valeur["role"], rec, "inspection")

    def _in_game_event(self, data, rec):
        kind = data.get("kind")
        if kind == "clock_changed":
            self._horloge(data.get("clock") or data)
        elif kind == "round_started":
            self._nouvelle_manche(data.get("round_id"))
        elif kind == "vote_closed":
            self._vote_clos(data, rec)
        elif kind == "dawn":
            self._aube(data, rec)
        elif kind == "night_death":
            nom = _nom(data.get("victim") or data.get("name") or data)
            if nom:
                self.joueur(nom, vivant=False)
        elif kind == "captain_changed":
            nom = _nom(data.get("captain") or data.get("name") or data)
            if nom:
                for node in self.noeuds.values():
                    node.pop("capitaine", None)
                self.joueur(nom, capitaine=True)
        elif kind == "bonus_granted":
            noms = data.get("names") or data.get("suspects") or []
            for nom in noms if isinstance(noms, list) else []:
                if _nom(nom):
                    self.soupcon(self.joueur(_nom(nom)), "cite_par_indice", rec)

    def _vote_clos(self, data, rec):
        elimine = data.get("eliminated") or data.get("elimine") or data.get("victim")
        nom = _nom(elimine)
        voix = data.get("votes") or data.get("tally") or {}
        if isinstance(voix, dict):
            for label, n in voix.items():
                if isinstance(n, (int, float)):
                    self.joueur(label, voix_dernier_conseil=n)
        if not nom:
            return
        jid = self.joueur(nom, vivant=False)
        self.arete(jid, "EST_MORT_A", self.noeud(LIEU_CONSEIL, "Lieu", "campfire",
                                                 kind="campfire"),
                   rec, "éliminé au conseil", poids=1.0, cause="conseil")
        role = _role_de(elimine) or data.get("role") or data.get("revealed_role")
        if role:
            self.fixe_role(jid, role, rec, "rôle révélé au conseil")

    def _aube(self, data, rec):
        morts = data.get("deaths") or data.get("dead") or data.get("victims") or []
        if isinstance(morts, dict):
            morts = [{"name": k, "role": v} for k, v in morts.items()]
        inconnus = [c for c in self.cadavres if not c.get("nom")
                    and rec.get("t", 0) - (c["t"] or 0) < 3600]
        for mort in morts if isinstance(morts, list) else []:
            nom = _nom(mort)
            if not nom:
                continue
            jid = self.joueur(nom, vivant=False)
            if _role_de(mort):
                self.fixe_role(jid, _role_de(mort), rec, "rôle révélé à l'aube")
            if len(morts) == 1 and len(inconnus) == 1:
                self.arete(jid, "EST_MORT_A", inconnus[0]["lieu"], rec,
                           "seul cadavre vu cette nuit", poids=0.6, cause="nuit")

    def _nouvelle_manche(self, round_id):
        if round_id is None or round_id == self.manche:
            return
        # Rôles et soupçons valent pour une manche ; domiciles et lieux restent.
        durables = {"HABITE", "VU_PRES_DE"}
        for key, edge in list(self.aretes.items()):
            if edge["rel"] not in durables:
                self.archives.append(self.aretes.pop(key))
        self.logcote.clear()
        self.indices.clear()
        self.certain.clear()
        self.cadavres.clear()
        self.paroles.clear()
        self.accusations.clear()
        self.miroirs.clear()
        self.potions_utilisees.clear()
        self.nb_inspections = 0
        for node in self.noeuds.values():
            node.pop("vivant", None)
            node.pop("voix_dernier_conseil", None)
        self.manche = round_id

    # ------------------------------------------------------------------ lecture par le moteur

    def id_joueur(self, nom):
        return "joueur:" + nom

    def vivant(self, joueur_id):
        return self.noeuds.get(joueur_id, {}).get("vivant") is not False

    def loups_connus(self):
        """Noms des loups certains, hors soi : pour un loup, ses partenaires."""
        return sorted(self.noeuds[j]["label"] for j, r in self.certain.items()
                      if r == "role:loup" and j != self.moi and j in self.noeuds)

    def capitaine(self):
        """Nom du Capitaine connu, ou None."""
        return next((n["label"] for n in self.noeuds.values()
                     if n["type"] == "Joueur" and n.get("capitaine")), None)

    def pretentions(self, joueur_id):
        """Rôles que ce joueur a dit avoir : {"voyante", ...}."""
        return {dst.split(":", 1)[1] for (src, rel, dst) in self.aretes
                if src == joueur_id and rel == "PRETEND_ETRE"}

    def nb_accusations(self, joueur_id):
        """Accusations entendues contre ce joueur, hors les nôtres."""
        return sum(e["count"] for (src, rel, dst), e in self.aretes.items()
                   if rel == "ACCUSE" and dst == joueur_id and src != self.moi)

    def accuse_recemment(self, src, dst, depuis_t):
        edge = self.aretes.get((src, "ACCUSE", dst))
        return bool(edge and (edge.get("last_t") or 0) >= depuis_t)

    def inspections(self):
        """Rôles appris par nos inspections de Voyante : {nom: rôle}."""
        out = {}
        for (src, rel, dst), edge in self.aretes.items():
            if rel == "A_LE_ROLE" and any(p.get("regle") == "inspection" for p in edge["preuves"]):
                out[self.noeuds[src]["label"]] = dst.split(":", 1)[1]
        return out

    # ------------------------------------------------------------------ export

    def _aretes_soupcon(self):
        loup = self.role("loup")
        for jid, node in self.noeuds.items():
            if node["type"] != "Joueur" or jid == self.moi or jid in self.certain:
                continue
            yield {
                "src": jid, "rel": "SOUPCONNE_ETRE", "dst": loup,
                "weight": round(self.proba_loup(jid), 3), "manche": self.manche,
                "count": len(self.indices.get(jid, [])), "preuves": self.indices.get(jid, []),
            }

    def en_dict(self):
        return {
            "run_t": time.time(),
            "manche": self.manche,
            "jour": self.jour,
            "minute": self.minute,
            "moi": self.moi,
            "noeuds": list(self.noeuds.values()),
            "aretes": list(self.aretes.values()) + list(self._aretes_soupcon()),
            "archives": len(self.archives),
        }

    def ecrire_json(self, chemin):
        chemin = Path(chemin)
        tmp = chemin.with_suffix(chemin.suffix + ".tmp")
        tmp.write_text(json.dumps(self.en_dict(), ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(chemin)  # jamais de fichier à moitié écrit

    def en_cypher(self):
        """Script Neo4j : `cypher-shell < graphe.cypher`, ou à coller dans Neo4j Browser."""

        def props(d, exclure=()):
            items = []
            for k, v in d.items():
                if k in exclure or isinstance(v, (dict, list)) or v is None:
                    continue
                items.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            return "{" + ", ".join(items) + "}"

        lignes = []
        for node in self.noeuds.values():
            lignes.append(f"MERGE (n:{node['type']} {{id: {json.dumps(node['id'], ensure_ascii=False)}}})"
                          f" SET n += {props(node, ('type',))};")
        for edge in self.en_dict()["aretes"]:
            lignes.append(
                f"MATCH (a {{id: {json.dumps(edge['src'], ensure_ascii=False)}}}),"
                f" (b {{id: {json.dumps(edge['dst'], ensure_ascii=False)}}})"
                f" MERGE (a)-[r:{edge['rel']}]->(b)"
                f" SET r += {props(edge, ('src', 'dst', 'rel'))};"
            )
        return "\n".join(lignes) + "\n"

    def resume(self, seuil=0.0):
        """Texte court pour un prompt : soupçons, rôles connus, morts."""
        lignes = []
        joueurs = [n for n in self.noeuds.values() if n["type"] == "Joueur" and n["id"] != self.moi]
        joueurs.sort(key=lambda n: -self.proba_loup(n["id"]))
        for node in joueurs:
            jid = node["id"]
            if jid in self.certain:
                etat = "rôle certain : " + self.certain[jid].split(":", 1)[1]
            else:
                p = self.proba_loup(jid)
                if p < seuil:
                    continue
                motifs = sorted({i["regle"] for i in self.indices.get(jid, [])})
                etat = f"p(loup)={p:.2f}" + (f" ({', '.join(motifs)})" if motifs else "")
            if node.get("vivant") is False:
                etat += ", mort"
            lignes.append(f"- {node['label']} : {etat}")
        return "\n".join(lignes)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Recalcule le graphe d'un journal JSONL.")
    parser.add_argument("journal", help="Fichier traces/<run>.jsonl")
    parser.add_argument("--cypher", action="store_true", help="Écrit aussi un script Neo4j.")
    opts = parser.parse_args()
    g = Graphe.depuis_jsonl(opts.journal)
    sortie = Path(opts.journal).with_suffix(".graphe.json")
    g.ecrire_json(sortie)
    print(f"{len(g.noeuds)} nœuds, {len(g.en_dict()['aretes'])} arêtes → {sortie}")
    if opts.cypher:
        cypher = Path(opts.journal).with_suffix(".cypher")
        cypher.write_text(g.en_cypher(), encoding="utf-8")
        print("Neo4j →", cypher)
    print(g.resume())
