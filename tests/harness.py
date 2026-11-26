import asyncio

from tests.sim import Sim
from village.body import Body
from village.net import Session
from village.state import GameState
from village.worldmap import WorldMap


class Env:
    """Simulateur + agent connectés ; à utiliser avec `async with Env(...) as e`."""
    def __init__(self, **kw):
        self.sim = Sim(**kw)

    async def __aenter__(self):
        url = await self.sim.start()
        self.state = GameState(WorldMap())
        self.session = Session(url, "t", "test", self.state)
        self.body = Body(self.session)
        self.net = asyncio.create_task(self.session.run())
        while not self.state.alive:
            await self.state.wait_change(0.2)
        await asyncio.sleep(0.2)
        return self

    async def __aexit__(self, *a):
        self.net.cancel()
        await self.sim.stop()


def run(coro, timeout=60):
    return asyncio.run(asyncio.wait_for(coro, timeout))
