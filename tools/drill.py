"""Exercices en conditions réelles : python -m tools.drill <exercice> [args]
Exercices : look, goto REF [stop], sit [REF], stand, board, enter HOUSE, leave HOUSE, home, spin, say TEXT, emote GESTE"""
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from village.body import Body
from village.net import Session
from village.state import GameState
from village.worldmap import WorldMap

ROOT = Path(__file__).parent.parent


def brief(st):
    me = st.me
    return (f"pos=({st.world.pose[0]:.1f},{st.world.pose[1]:.1f},{st.world.pose[2]:.0f}°) fixe={st.world.fixed} posture={me.get('posture')} "
            f"gait={me.get('gait')} zones={me.get('zones')} heure={st.hour() and round(st.hour(),1)} "
            f"landmarks={len(st.world.landmarks)}")


async def run(args):
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    st = GameState(WorldMap(ROOT / "data" / "village_map.json"))
    logf = open(ROOT / "logs" / f"drill-{int(time.time())}.jsonl", "w")
    s = Session(os.environ["GAME_WS_URL"], os.environ["TEAM_TOKEN"], "drill-1", st, log=logf)
    body = Body(s)
    net = asyncio.create_task(s.run())
    try:
        while not st.alive:
            await st.wait_change(0.5)
        await asyncio.sleep(0.5)
        print("début :", brief(st))
        cmd = args[0]
        if cmd == "look":
            print({k: (v["kind"], round(v["bearing_deg"]), round(v["distance_m"], 1)) for k, v in st.visible.items()})
        elif cmd == "goto":
            print("arrivé" if await body.goto(args[1], stop=float(args[2]) if len(args) > 2 else 1.5) else "ECHEC")
        elif cmd == "sit":
            print((await body.sit(args[1] if len(args) > 1 else None)))
        elif cmd == "sleep":
            print(await body.sleep(args[1] if len(args) > 1 else None))
        elif cmd == "stand":
            print(await body.stand())
        elif cmd == "board":
            print(await body.s.send('act', {'action': 'read_board', 'target_ref': 'board'}))
        elif cmd == "enter":
            print("dedans" if await body.enter(args[1]) else "ECHEC", )
        elif cmd == "leave":
            print("dehors" if await body.leave(args[1]) else "ECHEC")
        elif cmd == "home":
            print(await body.return_home())
            await asyncio.sleep(11)
        elif cmd == "localize":
            print("localisé" if await body.localize() else "ECHEC")
        elif cmd == "explore":
            kind = args[1] if len(args) > 1 else None
            budget = float(args[2]) if len(args) > 2 else 90
            print("trouvé" if await body.explore(until=(lambda: body.w.of_kind(kind)) if kind else None, budget=budget) else "budget épuisé")
            print({k: v["kind"] for k, v in body.w.landmarks.items() if v["kind"] not in ("door", "house", "bed")})
        elif cmd == "spin":
            await body.scan_around()
        elif cmd == "say":
            print(await body.speak(" ".join(args[1:])))
        elif cmd == "emote":
            print(await body.emote(args[1]))
        await asyncio.sleep(0.5)
        print("fin    :", brief(st))
        print("visibles:", {k: (v["kind"], round(v["bearing_deg"]), round(v["distance_m"], 1)) for k, v in st.visible.items() if v["kind"] in ("house", "door", "bed", "bench", "board", "stone", "campfire")})
    finally:
        await body.stop()
        st.world.save()
        net.cancel()


asyncio.run(run(sys.argv[1:] or ["look"]))
