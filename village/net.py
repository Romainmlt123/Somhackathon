"""Connexion WebSocket : lecture sans blocage, reconnexion, commandes avec accusé de réception.

Les messages de perception (vision, self, scan) sont appliqués immédiatement à l'état : la file des
événements ne reçoit que ce que le cerveau doit traiter, ce qui évite la saturation (code 1013)
même pendant une marche où le serveur envoie des dizaines de `vision` par seconde.
"""
import asyncio
import json
import time
import uuid

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .state import GameState


class Fatal(Exception):
    pass


class Session:
    def __init__(self, url, token, version, state=None, log=None):
        self.url, self.token, self.version = url, token, version
        self.state = state or GameState()
        self.events = asyncio.Queue()
        self.pending = {}       # command_id -> (frame JSON, future)
        self.ws = None
        self.log = log          # fichier JSONL optionnel pour tout enregistrer
        self.on_connect = []    # callbacks async appelés après chaque (re)connexion

    # ---- commandes
    async def send(self, kind, data, timeout=6.0):
        """Envoie une commande et attend son command_result. Renvoie le dict du résultat,
        ou {"ok": None, "code": "timeout"} (la commande reste rejouable à l'identique)."""
        cid = uuid.uuid4().hex[:12]
        frame = json.dumps({"type": kind, "command_id": cid, "data": data})
        fut = asyncio.get_running_loop().create_future()
        self.pending[cid] = (frame, fut)
        t0 = time.time()
        while self.ws is None and time.time() - t0 < timeout:
            await asyncio.sleep(0.05)
        try:
            if self.ws is not None:
                await self.ws.send(frame)
            return await asyncio.wait_for(asyncio.shield(fut), max(0.1, timeout - (time.time() - t0)))
        except (asyncio.TimeoutError, ConnectionClosed):
            return {"command_id": cid, "ok": None, "code": "timeout"}
        finally:
            if fut.done():
                self.pending.pop(cid, None)

    def fire(self, kind, data):
        """Envoie sans attendre le résultat (déplacements fréquents)."""
        return asyncio.ensure_future(self.send(kind, data, timeout=3.0))

    # ---- boucle réseau
    async def run(self):
        while True:
            try:
                await self._once()
            except InvalidStatus as exc:
                if exc.response.status_code in (401, 409):
                    raise Fatal(f"Connexion refusée ({exc.response.status_code}) : jeton invalide ou autre agent connecté.")
            except (OSError, ConnectionClosed, asyncio.TimeoutError):
                pass
            self.ws = None
            self.state.connected = False
            await asyncio.sleep(1.5)

    async def _once(self):
        async with connect(self.url, additional_headers={"Authorization": "Bearer " + self.token},
                           max_size=2 ** 20, ping_interval=10) as ws:
            await ws.send(json.dumps({"type": "hello", "agent_version": self.version}))
            self.ws = ws
            self.state.connected = True
            for frame, fut in list(self.pending.values()):   # rejeu des commandes sans accusé
                await ws.send(frame)
            for cb in self.on_connect:
                await cb()
            async for message in ws:
                if self.log:
                    self.log.write(message + "\n")
                frame = json.loads(message)
                if frame["type"] == "command_result":
                    entry = self.pending.get(frame["data"]["command_id"])
                    if entry and not entry[1].done():
                        entry[1].set_result(frame["data"])
                if self.state.apply(frame):
                    self.events.put_nowait(frame)
