"""Exemple autonome. Un agent avance, vote au conseil et rentre dormir la nuit."""

import argparse
import asyncio
import time
from collections import deque
import os
import random
from pathlib import Path

import journal
from client import Agent
from graphe import Graphe
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosed, InvalidStatus


class Explorer:
    def __init__(self, model=None, max_calls=3):
        self.model, self.calls_left = model, max_calls
        self.remarks = deque(maxlen=4)
        self.vote_commands = {}
        self.personal = {}
        self.requests = {}
        self.voted = set()
        self.turn_pending = False
        # La nuit : lits en vue, envie de dormir, demande de retour déjà faite.
        self.beds = {}
        self.resting = self.asked_tonight = False
        self.return_command = self.sleep_command = self.stand_command = None
        # Observabilité : graphe de connaissances nourri par le journal, état écrit régulièrement.
        self.graphe = Graphe()
        journal.subscribe(self.graphe.observe)
        self.last_dump = 0.0

    async def decide(self, frame, send):
        await self._decide(frame, send)
        if time.time() - self.last_dump >= 15:
            self.dump()

    def dump(self):
        """Écrit la mémoire interne dans le journal et le graphe à côté du journal."""
        self.last_dump = time.time()
        journal.state(
            name=self.personal.get("name"),
            posture=self.personal.get("posture"),
            zones=self.personal.get("zones"),
            resting=self.resting,
            beds_known=self.beds,
            remarks=list(self.remarks),
            open_requests=sorted(self.requests),
            voted=sorted(self.voted),
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
            self.remarks.clear()
            self.vote_commands.clear()
            self.voted.clear()
            self.turn_pending = False
            self.return_command = self.sleep_command = self.stand_command = None
            self.beds = {
                v["ref"]: v["distance_m"]
                for v in data.get("visible", [])
                if v["kind"] == "bed"
            }
            print(
                "Village :", data["status"], self.personal.get("name", ""), flush=True
            )
            minute = (data.get("clock") or {}).get("minute", 720)
            if data.get("round") and (minute >= 1320 or minute < 480):
                await self.go_to_bed(send)
            elif self.personal:
                # Le balayage de cet instantané relance la marche, s’il y en a un.
                await self.get_up(send, stride=False)
            if data.get("scan"):
                await self.walk(data["scan"], send)
        elif kind == "self":
            was_waiting = self.waiting()
            self.personal = data
            arrived = "home" in data.get("zones", [])
            if was_waiting and not self.waiting() and not arrived:
                # Retour annulé : l’exemple n’insiste pas et repart explorer.
                self.resting = False
                await self.stride(send)
            elif (
                data.get("motion_reason") == "blocked"
                and not self.turn_pending
                and not self.staying()
            ):
                journal.why("turn", reason="blocked")
                await self.turn(send)
            await self.lie_down(send)
        elif kind == "vision":
            for seen in data["entered"] + data["updated"]:
                if seen["kind"] == "bed":
                    self.beds[seen["ref"]] = seen["distance_m"]
            for ref in data["left"]:
                self.beds.pop(ref, None)
            await self.lie_down(send)
        elif kind == "scan":
            await self.walk(data, send)
        elif kind == "decision_request":
            self.requests[data["request_id"]] = data
        elif kind == "decision_closed":
            self.requests.pop(data["request_id"], None)
        elif kind == "sound" and data.get("kind") == "speech":
            self.remarks.append(data["text"][:180])
        elif kind == "command_result":
            request_id = self.vote_commands.pop(data["command_id"], None)
            if request_id and data.get("code") == "outside_council":
                self.voted.discard(request_id)
            if data["command_id"] == self.turn_pending:
                self.turn_pending = False
                await self.stride(send)
            elif data["command_id"] == self.return_command:
                self.return_command = None
                if not data["ok"]:
                    # Demande refusée, par exemple moins d’une minute après la précédente.
                    self.resting = False
                    await self.stride(send)
            elif data["command_id"] == self.sleep_command and data["ok"]:
                self.sleep_command = None
            elif data["command_id"] == self.stand_command:
                self.stand_command = None
                await self.stride(send)
            return
        elif kind == "game_event":
            print(data.get("text", data["kind"]), flush=True)
            if data["kind"] == "scheduled_step" and data["step"] == "nightfall":
                await self.go_to_bed(send)
            elif data["kind"] == "scheduled_step" and data["step"] == "village_wakes":
                await self.get_up(send)
        if "council" in self.personal.get("zones", []):
            for req in self.requests.values():
                key = req["request_id"]
                votes = next(
                    (a["choices"] for a in req["actions"] if a["action"] == "vote"), []
                )
                if votes and key not in self.voted:
                    choice = random.choice(votes)["choice_id"]
                    source = "random"
                    seconds = (req["deadline_ms"] - time.time() * 1000) / 1000
                    if self.model and self.calls_left and seconds > 2:
                        from appel_modele import choose

                        self.calls_left -= 1
                        try:
                            choice = await asyncio.to_thread(
                                choose,
                                self.model,
                                req["kind"],
                                self.personal.get("name"),
                                self.personal.get("role"),
                                votes,
                                list(self.remarks),
                                min(8, seconds - 1),
                                self.graphe.resume(),
                            )
                            source = "llm"
                        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                            print("Décision locale pour ce scrutin.", flush=True)
                            source = "random_after_llm_error:" + type(exc).__name__
                    journal.why(
                        "vote",
                        request_id=key,
                        kind=req["kind"],
                        choice_id=choice,
                        label=next(
                            (v["label"] for v in votes if v["choice_id"] == choice), None
                        ),
                        source=source,
                        llm_calls_left=self.calls_left,
                        suspicions=self.graphe.resume(),
                    )
                    cid = await send(
                        "act",
                        dict(
                            action="vote",
                            request_id=key,
                            choice_id=choice,
                        ),
                    )
                    self.vote_commands[cid] = key
                    self.voted.add(key)

    async def turn(self, send):
        self.turn_pending = await send(
            "turn", {"angle_deg": random.choice([-65, 80, 115])}
        )

    def waiting(self):
        """Un retour à la maison est demandé : tout déplacement l’annulerait."""
        return bool(
            self.return_command
            or "home_return_at_ms" in self.personal.get("powers", {})
        )

    def staying(self):
        return self.resting or self.waiting()

    async def stride(self, send):
        if self.personal.get("posture") == "standing" and not self.staying():
            await send("move", {"gait": "walk", "bearing_deg": 0})

    async def go_to_bed(self, send):
        """À 22 h, sans savoir où est sa maison, l’exemple demande à y être ramené."""
        if not self.personal:
            return
        if "home" in self.personal.get("zones", []) or self.waiting():
            self.resting = True
        elif not self.asked_tonight:
            self.resting = self.asked_tonight = True
            journal.why("return_home", reason="night", zones=self.personal.get("zones"))
            self.return_command = await send("act", {"action": "return_home"})
        await self.lie_down(send)

    async def lie_down(self, send):
        if (
            self.resting
            and self.beds
            and not self.sleep_command
            and "home" in self.personal.get("zones", [])
            and self.personal.get("posture") == "standing"
        ):
            # On arrive chez soi tourné vers son lit, à portée : c’est le plus proche.
            # Un refus n’est pas retenté : l’exemple passe alors la nuit debout.
            journal.why("sleep", bed=min(self.beds, key=self.beds.get), beds=self.beds)
            self.sleep_command = await send(
                "act",
                {"action": "sleep", "target_ref": min(self.beds, key=self.beds.get)},
            )

    async def get_up(self, send, stride=True):
        self.resting = self.asked_tonight = False
        self.sleep_command = None
        if self.personal.get("posture") == "sleeping":
            self.stand_command = await send("act", {"action": "stand"})
        elif stride:
            await self.stride(send)

    async def walk(self, scan, send):
        if (
            self.turn_pending
            or not self.personal
            or self.personal.get("posture") in ("sleeping", "sitting")
            or self.staying()
        ):
            return
        sectors = scan["distances_m"]
        center = len(sectors) // 2
        front = [
            d for d in sectors[max(0, center - 2) : center + 3] if d is not None
        ]
        if front and min(front) < 1.4:
            journal.why("turn", reason="obstacle", front_m=min(front))
            await self.turn(send)
        elif self.personal.get("gait") == "stop":
            await send("move", {"gait": "walk", "bearing_deg": 0})


async def main():
    load_dotenv(Path(__file__).with_name(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model", help="Modèle OpenRouter payant pour choisir au conseil."
    )
    parser.add_argument(
        "--max-appels",
        type=int,
        default=3,
        help="Budget en nombre d’appels par lancement.",
    )
    opts = parser.parse_args()
    if opts.max_appels < 0:
        parser.error("Le budget doit être positif ou nul.")
    agent = Agent(
        os.environ["GAME_WS_URL"],
        os.environ["TEAM_TOKEN"],
        "explorateur-2"
        if not opts.model
        else f"conseil-1/{opts.model}/{opts.max_appels}",
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
                    f"Connexion refusée ({exc.response.status_code}). Vérifiez le jeton ou l’autre agent."
                )
        except (OSError, ConnectionClosed, BufferError):
            pass
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
