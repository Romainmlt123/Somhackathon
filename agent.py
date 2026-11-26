"""Agent du village : le corps de l'exemple, piloté par le moteur de règles (`moteur.py`).

Les règles appliquées sont celles de `Régles/ETUDE_LOUP_GAROU.md` ; chaque décision est
journalisée avec son numéro de règle (`journal.why(..., regle="V2")`).
"""

import argparse
import asyncio
import os
import random
import re
import time
from collections import deque
from pathlib import Path

import epreuves
import journal
import moteur
from client import Agent
from graphe import Graphe
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed, InvalidStatus

# Zone où l'habitant doit se trouver pour répondre à chaque invitation.
ZONE_REQUISE = {
    "council_vote": "council",
    "captain_election": "council",
    "challenge_answer": "challenge",
    "seer_inspect": "home",
    "witch_potion": "home",
}
CODES_A_REESSAYER = {"outside_council", "outside_challenge", "outside_home", "out_of_reach"}
ERREURS_MODELE = (OSError, ValueError, KeyError, IndexError, TypeError)
TIMEOUT_VOTE_S = 8
TIMEOUT_PAROLE_S = 4
TIMEOUT_EPREUVE_S = 10


class Explorer:
    def __init__(self, model=None, max_calls=3):
        self.model, self.calls_left = model, max_calls
        self.remarks = deque(maxlen=4)
        self.personal = {}
        self.requests = {}
        self.visible = {}               # ref → observation courante
        self.round_id = None
        self.turn_pending = False
        # La nuit : lits en vue, envie de dormir, demande de retour en cours.
        self.beds = {}
        self.resting = False
        self.return_command = self.sleep_command = self.stand_command = None
        self.action_command = None      # transform ou attack en attente de réponse
        self.request_commands = {}      # command_id → request_id
        self.answered = set()           # invitations servies
        self.in_progress = set()        # invitations en cours de calcul
        self.tasks = set()
        self.speaking = asyncio.Lock()
        self.last_objective = None
        # Observabilité : graphe de connaissances nourri par le journal, état écrit régulièrement.
        self.graphe = Graphe()
        journal.subscribe(self.graphe.observe)
        self.moteur = moteur.Moteur(self.graphe, secrets=(os.environ.get("TEAM_TOKEN"),))
        self.last_dump = 0.0

    # ------------------------------------------------------------------ lecture de l'état

    def nom(self):
        return self.personal.get("name")

    def role(self):
        return self.personal.get("role")

    def minute(self):
        return self.graphe.minute

    def zones(self):
        return self.personal.get("zones", [])

    def objectif(self):
        scrutin = any(
            r.get("kind") in ("council_vote", "captain_election")
            and r["request_id"] not in self.answered
            for r in self.requests.values()
        )
        epreuve = self.moteur.epreuve
        return moteur.objectif(
            self.minute(), self.role(), self.personal.get("form"),
            epreuve and epreuve["lieu"], scrutin, self.moteur.chasse_finie,
        )

    def can_llm(self):
        return bool(self.model and self.calls_left > 0)

    async def llm(self, fn, *args):
        self.calls_left -= 1
        return await asyncio.to_thread(fn, *args)

    def tache(self, coro):
        """Lance une décision longue sans bloquer la lecture des messages."""
        task = asyncio.create_task(self._sans_echec(coro))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _sans_echec(self, coro):
        try:
            await coro
        except Exception as exc:
            journal.why("tache_erreur", error=repr(exc))

    # ------------------------------------------------------------------ boucle

    async def decide(self, frame, send):
        await self._decide(frame, send)
        if time.time() - self.last_dump >= 15:
            self.dump()

    def dump(self):
        """Écrit la mémoire interne dans le journal et le graphe à côté du journal."""
        self.last_dump = time.time()
        journal.state(
            name=self.nom(),
            role=self.role(),
            posture=self.personal.get("posture"),
            zones=self.zones(),
            objective=self.last_objective,
            resting=self.resting,
            epreuve=self.moteur.epreuve,
            chasse_finie=self.moteur.chasse_finie,
            remarks=list(self.remarks),
            open_requests=sorted(self.requests),
            answered=sorted(self.answered),
            llm_calls_left=self.calls_left,
        )
        if journal.ENABLED:
            try:
                self.graphe.ecrire_json(journal.path().with_suffix(".graphe.json"))
            except OSError:
                pass

    async def _decide(self, frame, send):
        kind, data = frame["type"], frame["data"]
        if kind == "snapshot":
            self.personal = data.get("self", {})
            self.requests = {r["request_id"]: r for r in data.get("requests", [])}
            self.visible = {v["ref"]: v for v in data.get("visible", [])}
            self.round_id = (data.get("round") or {}).get("round_id")
            self.remarks.clear()
            self.request_commands.clear()
            self.answered.clear()
            self.turn_pending = False
            self.resting = False
            self.return_command = self.sleep_command = self.stand_command = None
            self.action_command = None
            self.beds = {ref: v["distance_m"] for ref, v in self.visible.items() if v["kind"] == "bed"}
            print("Village :", data["status"], self.nom() or "", self.role() or "", flush=True)
            await self.piloter(send)
            if data.get("scan"):
                await self.walk(data["scan"], send)
            return
        if kind == "self":
            was_wolf = moteur.forme_loup(self.personal.get("form"))
            self.personal = data
            if was_wolf and not moteur.forme_loup(data.get("form")):
                # L3 : la meute a repris forme humaine (6 h, ou victime dans une maison).
                self.moteur.chasse_finie = True
                journal.why("chasse_finie", regle="L3")
            if (
                data.get("motion_reason") == "blocked"
                and not self.turn_pending
                and not self.staying()
            ):
                journal.why("turn", reason="blocked")
                await self.turn(send)
            await self.lie_down(send)
        elif kind == "vision":
            for seen in data["entered"] + data["updated"]:
                self.visible[seen["ref"]] = seen
                if seen["kind"] == "bed":
                    self.beds[seen["ref"]] = seen["distance_m"]
            for ref in data["left"]:
                self.visible.pop(ref, None)
                self.beds.pop(ref, None)
            await self.lie_down(send)
        elif kind == "scan":
            await self.walk(data, send)
        elif kind == "decision_request":
            self.requests[data["request_id"]] = data
            self.answered.discard(data["request_id"])   # une modification remplace l'invitation
        elif kind == "decision_closed":
            self.requests.pop(data["request_id"], None)
        elif kind == "sound" and data.get("kind") == "speech":
            self.remarks.append(data["text"][:180])
            await self.parler(send, self.moteur.entendre(data, self.nom(), self.role()))
        elif kind == "command_result":
            await self.resultat(data, send)
            return
        elif kind == "game_event":
            print(data.get("text", data["kind"]), flush=True)
            self.moteur.evenement(data)
            if data["kind"] == "round_started":
                self.round_id = data.get("round_id")
            elif data["kind"] == "scheduled_step" and data.get("step") == "village_wakes":
                await self.get_up(send)
        await self.piloter(send)

    async def resultat(self, data, send):
        cid, ok = data["command_id"], data["ok"]
        request_id = self.request_commands.pop(cid, None)
        if request_id and not ok and data.get("code") in CODES_A_REESSAYER:
            # Refus hors zone : on renverra avec un nouvel identifiant une fois sur place.
            self.answered.discard(request_id)
        if cid == self.action_command:
            self.action_command = None
            if not ok:
                journal.why("action_refusee", code=data.get("code"))
        if cid == self.turn_pending:
            self.turn_pending = False
            await self.stride(send)
        elif cid == self.return_command:
            self.return_command = None
            if not ok:
                # Refusé (moins d'une minute après la précédente) : on reste sur place,
                # `piloter` redemandera dès que `home_return_ready_ms` sera passé.
                journal.why("return_home_refuse", code=data.get("code"))
        elif cid == self.sleep_command and ok:
            self.sleep_command = None
        elif cid == self.stand_command:
            self.stand_command = None
            await self.stride(send)

    # ------------------------------------------------------------------ règles

    async def piloter(self, send):
        """Applique les règles à chaque message : invitations, horaires, parole, chasse."""
        await self.servir_invitations(send)
        if not self.personal:
            return
        obj = self.objectif()
        if obj.lieu != self.last_objective:
            self.last_objective = obj.lieu
            journal.why("objectif", regle=obj.regle, lieu=obj.lieu, motif=obj.motif,
                        heure=moteur.heure(self.minute()))
        if obj.lieu == "maison":
            if not self.resting or (
                "home" not in self.zones() and not self.waiting() and self.peut_rentrer()
            ):
                await self.go_to_bed(send, obj.regle)
        elif self.resting or self.personal.get("posture") == "sleeping":
            await self.get_up(send)
        elif obj.lieu == "stone":
            await self.transformer(send)
        elif obj.lieu == "chasse":
            await self.chasser(send)

        minute, zones = self.minute(), self.zones()
        if self.moteur.peut_parler() and minute is not None:
            if "council" in zones and moteur.CONSEIL <= minute < moteur.VOTE_FIN:
                await self.parler(send, self.moteur.au_conseil(self.nom(), self.role()))
            elif "challenge" in zones:
                await self.parler(send, self.moteur.a_l_epreuve(self.nom(), self.role()))

    async def servir_invitations(self, send):
        """C1, C3, C4 : répondre depuis la bonne zone, et voter tard mais avant la clôture."""
        now_ms = time.time() * 1000
        for req in list(self.requests.values()):
            rid, kind = req["request_id"], req.get("kind")
            if rid in self.answered or rid in self.in_progress:
                continue
            zone = ZONE_REQUISE.get(kind)
            if zone and self.personal and zone not in self.zones():
                continue
            if kind in ("council_vote", "captain_election"):
                restant = (req["deadline_ms"] - now_ms) / 1000
                if restant > moteur.marge_vote_s(self.can_llm()):
                    continue
            self.in_progress.add(rid)
            self.tache(self.servir(req, send))

    async def servir(self, req, send):
        rid = req["request_id"]
        try:
            reponse = await self.reponse(req)
            if reponse is None:
                self.answered.add(rid)
                return
            action, champs = reponse
            cid = await send("act", {"action": action, "request_id": rid, **champs})
            self.request_commands[cid] = rid
            self.answered.add(rid)
        finally:
            self.in_progress.discard(rid)

    async def reponse(self, req):
        """(action, champs) à envoyer pour une invitation, ou None."""
        kind = req.get("kind")
        actions = {a["action"]: a for a in req.get("actions") or []}
        moi, role = self.nom(), self.role()
        if kind in ("council_vote", "captain_election"):
            return await self.voter(req, actions.get("vote") or {})
        if kind == "seer_inspect":
            choix = (actions.get("inspect") or {}).get("choices") or []
            c = moteur.choisir_inspection(self.graphe, moi, choix)
            journal.why("inspect", regle=c.regle, motif=c.motif, choice_id=c.choice_id)
            return ("inspect", {"choice_id": c.choice_id}) if c.choice_id else None
        if kind in ("witch_potion", "witch_self_rescue"):
            action, choice_id, regle, motif = moteur.choisir_potion(
                self.graphe, moi, list(actions.values()), req.get("allow_abstain", False))
            journal.why("potion", regle=regle, motif=motif, action=action, choice_id=choice_id)
            if action is None:
                return None
            return action, ({"choice_id": choice_id} if choice_id else {})
        if kind == "captain_succession":
            choix = (actions.get("name_successor") or {}).get("choices") or []
            c = moteur.choisir_successeur(self.graphe, moi, role, choix)
            journal.why("successeur", regle=c.regle, motif=c.motif, choice_id=c.choice_id)
            return ("name_successor", {"choice_id": c.choice_id}) if c.choice_id else None
        if kind == "challenge_answer":
            return await self.repondre_epreuve(req, actions.get("answer_challenge"))
        return None

    async def voter(self, req, action):
        """C2, C8, V2, V7, L9, L10 : les règles choisissent, le modèle départage si c'est serré."""
        choix = action.get("choices") or []
        moi, role = self.nom(), self.role()
        c = moteur.choisir_vote(self.graphe, moi, role, choix, req.get("kind"))
        choice_id, source = c.choice_id, "regles"
        restant = (req["deadline_ms"] - time.time() * 1000) / 1000
        if not c.sur and self.can_llm() and restant - moteur.MARGE_VOTE_S > 2:
            from appel_modele import choose

            try:
                propose = await self.llm(
                    choose, self.model, req["kind"], moi, role, choix, list(self.remarks),
                    min(TIMEOUT_VOTE_S, restant - moteur.MARGE_VOTE_S),
                    self.graphe.resume(), c.motif,
                )
                label = next((v["label"] for v in choix if v["choice_id"] == propose), None)
                proteges = self.graphe.pretentions(self.graphe.id_joueur(label or "")) & {"voyante", "sorciere"}
                # Le modèle ne peut pas faire voter pour soi (C2) ni contre un rôle protégé (V7).
                if label and label != moi and not (moteur.role_de(role) != "loup" and proteges):
                    choice_id, source = propose, "llm"
            except ERREURS_MODELE as exc:
                source = "regles_apres_erreur:" + type(exc).__name__
        journal.why(
            "vote", regle=c.regle, motif=c.motif, request_id=req["request_id"], kind=req.get("kind"),
            choice_id=choice_id, source=source, llm_calls_left=self.calls_left,
            suspicions=self.graphe.resume(),
        )
        if choice_id is None:
            return ("abstain", {}) if req.get("allow_abstain") else None
        return "vote", {"choice_id": choice_id}

    async def repondre_epreuve(self, req, action):
        """V10, C7, L12 : calcul local d'abord, modèle ensuite, réponse de repli enfin."""
        if not action:
            return None
        prompt, role = req.get("prompt") or "", self.role()
        champs = await asyncio.to_thread(epreuves.resoudre, prompt, action)
        source = champs.pop("solveur", "local") if champs else None
        if champs is None and self.can_llm():
            from appel_modele import resoudre_epreuve

            notes = "\n".join(self.moteur.memos + [f"{h} {o} : {t}" for h, o, t in self.moteur.entendu[-20:]])
            restant = (req["deadline_ms"] - time.time() * 1000) / 1000
            try:
                texte = await self.llm(resoudre_epreuve, self.model, role, prompt, action, notes,
                                       max(2, min(TIMEOUT_EPREUVE_S, restant - 3)))
                champs, source = self.champs_depuis_texte(texte, action), "llm"
            except ERREURS_MODELE as exc:
                source = "llm_erreur:" + type(exc).__name__
        if champs is None and action.get("format") == "choice" and action.get("choices"):
            # Repli : le plus suspect parmi les choix (désigner un coupable), sinon le premier.
            c = moteur.choisir_vote(self.graphe, self.nom(), "villageois", action["choices"])
            champs, source = {"choice_id": c.choice_id or action["choices"][0]["choice_id"]}, "repli"
        regle = "V10"
        if champs and moteur.role_de(role) == "loup" and moteur.LOUP_SABOTE_EPREUVES:
            champs, regle = epreuves.fausse_reponse(action, champs), "L12"
        if champs and "text" in champs and moteur.nettoyer(champs["text"], self.moteur.secrets) is None:
            champs, regle = None, "C7"
        journal.why("epreuve", regle=regle, source=source, reponse=champs, request_id=req["request_id"])
        return ("answer_challenge", champs) if champs else None

    @staticmethod
    def champs_depuis_texte(texte, action):
        lignes = (texte or "").strip().splitlines()
        texte = lignes[0].strip().strip('"«»` ') if lignes else ""
        if not texte:
            return None
        fmt, choix = action.get("format"), action.get("choices") or []
        if fmt == "text":
            return {"text": texte}
        numeros = [int(n) for n in re.findall(r"\d+", texte)]
        valides = [choix[n - 1]["choice_id"] for n in numeros if 1 <= n <= len(choix)]
        if fmt == "choice" and valides:
            return {"choice_id": valides[0]}
        if fmt == "multi_choice" and valides:
            return {"choice_ids": list(dict.fromkeys(valides))}
        return None

    async def parler(self, send, parole):
        if parole and self.personal and self.personal.get("posture") != "sleeping":
            self.tache(self._dire(send, parole))

    async def _dire(self, send, parole):
        """C5, C6, C7, L4 : reformuler si besoin, filtrer, espacer, dire."""
        role, texte = self.role(), parole.texte
        if parole.besoin_modele and self.can_llm():
            from appel_modele import repondre

            try:
                texte = await self.llm(repondre, self.model, self.nom(), role, parole.question,
                                       parole.texte, self.graphe.resume(0.3), TIMEOUT_PAROLE_S) or texte
            except ERREURS_MODELE:
                pass
        partenaires = self.graphe.loups_connus()
        final = moteur.nettoyer(texte, self.moteur.secrets, role, partenaires)
        if final is None and texte != parole.texte:
            final = moteur.nettoyer(parole.texte, self.moteur.secrets, role, partenaires)
        if final is None:
            journal.why("silence", regle=parole.regle, raison="filtre C7/L4", brouillon=parole.texte)
            return
        async with self.speaking:
            attente = moteur.PAROLE_ECART_S - (time.time() - self.moteur.derniere_parole)
            if attente > 0:
                await asyncio.sleep(attente)
            self.moteur.a_parle()
            journal.why("parole", regle=parole.regle, texte=final)
            await send("speak", {"volume": parole.volume, "text": final})

    # ------------------------------------------------------------------ loup (L1)

    def proie(self):
        """Habitant engagé le plus proche, hors loups connus."""
        loups = set(self.graphe.loups_connus())
        proies = [
            v for v in self.visible.values()
            if v["kind"] == "person" and v.get("engaged") is not False
            and v.get("name") not in loups and v.get("name") != self.nom()
        ]
        return min(proies, key=lambda v: v["distance_m"]) if proies else None

    async def transformer(self, send):
        pierres = [v for v in self.visible.values() if v["kind"] == "stone"]
        if not pierres or self.action_command:
            return
        pierre = min(pierres, key=lambda v: v["distance_m"])
        if pierre["distance_m"] <= moteur.PORTEE_ACTION_M and self.personal.get("posture") == "standing":
            journal.why("transform", regle="L1", distance_m=pierre["distance_m"])
            self.action_command = await send("act", {"action": "transform", "target_ref": pierre["ref"]})

    async def chasser(self, send):
        cible = self.proie()
        if not cible or self.action_command or not self.round_id:
            return
        if cible["distance_m"] <= moteur.PORTEE_ACTION_M:
            journal.why("attack", regle="L1", cible=cible.get("name"), distance_m=cible["distance_m"])
            self.action_command = await send(
                "act", {"action": "attack", "target_ref": cible["ref"], "round_id": self.round_id})

    # ------------------------------------------------------------------ corps

    async def turn(self, send, angle=None):
        if angle is None:
            angle = random.choice([-65, 80, 115])
        self.turn_pending = await send("turn", {"angle_deg": angle})

    def waiting(self):
        """Un retour à la maison est demandé : tout déplacement l'annulerait."""
        return bool(
            self.return_command
            or "home_return_at_ms" in self.personal.get("powers", {})
        )

    def peut_rentrer(self):
        pret = self.personal.get("powers", {}).get("home_return_ready_ms")
        return not self.return_command and (pret is None or time.time() * 1000 >= pret)

    def staying(self):
        return self.resting or self.waiting()

    async def stride(self, send):
        if self.personal.get("posture") == "standing" and not self.staying():
            await send("move", {"gait": "walk", "bearing_deg": 0})

    async def go_to_bed(self, send, regle="V1"):
        """V1 / L3 : rentrer chez soi par transport, puis se coucher."""
        if not self.personal:
            return
        self.resting = True
        if "home" not in self.zones() and not self.waiting() and self.peut_rentrer():
            journal.why("return_home", regle=regle, zones=self.zones())
            self.return_command = await send("act", {"action": "return_home"})
        await self.lie_down(send)

    async def lie_down(self, send):
        if (
            self.resting
            and self.beds
            and not self.sleep_command
            and "home" in self.zones()
            and self.personal.get("posture") == "standing"
        ):
            # On arrive chez soi tourné vers son lit, à portée : c'est le plus proche.
            bed = min(self.beds, key=self.beds.get)
            journal.why("sleep", regle="V1", bed=bed, beds=self.beds)
            self.sleep_command = await send("act", {"action": "sleep", "target_ref": bed})

    async def get_up(self, send, stride=True):
        self.resting = False
        self.sleep_command = None
        if self.personal.get("posture") == "sleeping":
            if not self.stand_command:
                self.stand_command = await send("act", {"action": "stand"})
        elif stride:
            await self.stride(send)

    def repere(self, obj):
        """Observation visible qui correspond à l'objectif, la plus proche."""
        if obj.lieu == "chasse":
            return self.proie()
        if obj.lieu in (None, "maison"):
            return None
        vus = [v for v in self.visible.values() if obj.lieu in (v["kind"], v.get("name"))]
        return min(vus, key=lambda v: v["distance_m"]) if vus else None

    def arrive(self, obj, cible):
        if obj.lieu == "campfire":
            return "council" in self.zones()
        if obj.lieu in ("stone", "chasse"):
            return cible["distance_m"] <= moteur.PORTEE_ACTION_M
        if self.moteur.epreuve and obj.lieu == self.moteur.epreuve["lieu"]:
            return "challenge" in self.zones()
        return cible["distance_m"] <= 3.0

    async def walk(self, scan, send):
        """Évite les obstacles, se dirige vers l'objectif s'il est en vue, sinon explore."""
        if (
            self.turn_pending
            or not self.personal
            or self.personal.get("posture") in ("sleeping", "sitting")
            or self.staying()
        ):
            return
        sectors = scan["distances_m"]
        center = len(sectors) // 2
        front = [d for d in sectors[max(0, center - 2): center + 3] if d is not None]
        obj = self.objectif()
        cible = self.repere(obj)
        if front and min(front) < 1.4 and not (cible and self.arrive(obj, cible)):
            journal.why("turn", reason="obstacle", front_m=min(front))
            await self.turn(send)
            return
        if cible is None:
            if self.personal.get("gait") == "stop":
                await send("move", {"gait": "walk", "bearing_deg": 0})
            return
        if self.arrive(obj, cible):
            if self.personal.get("gait") != "stop":
                journal.why("arrive", regle=obj.regle, lieu=obj.lieu, distance_m=cible["distance_m"])
                await send("move", {"gait": "stop"})
            return
        if abs(cible["bearing_deg"]) > 20:
            journal.why("cap", regle=obj.regle, lieu=obj.lieu, angle=cible["bearing_deg"],
                        distance_m=cible["distance_m"])
            await self.turn(send, cible["bearing_deg"])
        elif self.personal.get("gait") == "stop":
            await send("move", {"gait": "walk", "bearing_deg": 0})


async def main():
    load_dotenv(Path(__file__).with_name(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", help="Modèle payant pour départager un vote, répondre et les épreuves."
    )
    parser.add_argument(
        "--max-appels",
        type=int,
        default=3,
        help="Budget en nombre d'appels par lancement.",
    )
    opts = parser.parse_args()
    if opts.max_appels < 0:
        parser.error("Le budget doit être positif ou nul.")
    agent = Agent(
        os.environ["GAME_WS_URL"],
        os.environ["TEAM_TOKEN"],
        "regles-1" if not opts.model else f"regles-1/{opts.model}/{opts.max_appels}",
        Explorer(opts.model, opts.max_appels).decide,
    )
    journal.session("start", agent_version=agent.version, trace=str(journal.path()))
    print("Journal :", journal.path(), flush=True)
    while True:
        try:
            await agent.run_once()
        except InvalidStatus as exc:
            if exc.response.status_code in (401, 409):
                raise SystemExit(
                    f"Connexion refusée ({exc.response.status_code}). Vérifiez le jeton ou l'autre agent."
                )
        except (OSError, ConnectionClosed, BufferError):
            pass
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
