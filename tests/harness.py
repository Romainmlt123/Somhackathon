import asyncio
import json
import re
import tempfile
from pathlib import Path

from tests.sim import Sim
from village.body import Body
from village.brain import Brain
from village.net import Session
from village.state import GameState
from village.worldmap import WorldMap


class Env:
    """Simulateur + agent connectés ; à utiliser avec `async with Env(...) as e`."""
    def __init__(self, preload=False, **kw):
        self.sim = Sim(**kw)
        self.preload = preload
        self.start = kw.get("start", (0.0, -12.0))

    async def __aenter__(self):
        url = await self.sim.start()
        self.state = GameState(WorldMap())
        if self.preload:
            self.preload_map()
        self.session = Session(url, "t", "test", self.state)
        self.body = Body(self.session)
        self.net = asyncio.create_task(self.session.run())
        while not self.state.alive:
            await self.state.wait_change(0.2)
        await asyncio.sleep(0.2)
        return self

    def preload_map(self):
        """Carte déjà connue (exploration de jour) : repère de l'agent = repère du simulateur décalé de la position de départ."""
        ox, oy = -self.start[0], -self.start[1]
        lm = self.state.world.landmarks
        for h in self.sim.houses:
            lm[f"h{h.n}"] = {"x": h.cx + ox, "y": h.cy + oy, "kind": "house", "name": f"Maison nº {h.n}"}
            lm[f"d-h{h.n}"] = {"x": h.door[0] + ox, "y": h.door[1] + oy, "kind": "door", "of": f"h{h.n}"}
            lm[f"bed-h{h.n}"] = {"x": h.bed[0] + ox, "y": h.bed[1] + oy, "kind": "bed"}
        for ref, p in self.sim.benches.items():
            lm[ref] = {"x": p[0] + ox, "y": p[1] + oy, "kind": "bench"}
        for ref, p in self.sim.static.items():
            lm[ref] = {"x": p[0] + ox, "y": p[1] + oy, "kind": ref}
        self.state.world.pose, self.state.world.fixed = (0.0, 0.0, self.sim.heading), True

    async def __aexit__(self, *a):
        self.net.cancel()
        await self.sim.stop()


def run(coro, timeout=60):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def until(cond, timeout=60, step=0.2):
    t0 = asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time() - t0 < timeout:
        if cond():
            return True
        await asyncio.sleep(step)
    return False


class FakeLLM:
    """Modèle factice : `script(user_prompt) -> dict` ; par défaut le personnage attend."""
    model = "fake"

    def __init__(self, script=None):
        self.script = script
        self.calls, self.cost, self.tokens_in, self.tokens_out = 0, 0.0, 0, 0
        self.prompts = []

    async def chat(self, system, user):
        self.calls += 1
        self.prompts.append(user)
        d = self.script(user) if self.script else None
        if d is None:
            d = {"pensee": "fake", "action": "attendre", "duree": 1}
        return json.dumps(d), {"latency_s": 0}


def make_brain(env, script=None, max_calls=200):
    d = Path(tempfile.mkdtemp())
    llm = FakeLLM(script)
    br = Brain(env.session, env.body, llm, "test", d, d, max_calls=max_calls, min_interval=0.3)
    return br, llm


def choice_of(user, name):
    """Dans une invitation du contexte, renvoie l'identifiant du candidat `name` (« - id = Nom »)."""
    m = re.search(r"-\s*(?:\w+:)?(\S+)\s*=\s*" + re.escape(name), user)
    return m.group(1) if m else None
