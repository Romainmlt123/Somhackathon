"""Cockpit : tu tapes un ordre, l'agent l'exécute dans le jeu, et dit si ça a marché.
Lancer : .venv/bin/python cockpit.py     puis taper `aide`."""
import asyncio
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv

from village.body import Body
from village.net import Session
from village.state import GameState
from village.worldmap import WorldMap

ROOT = Path(__file__).parent
AIDE = """Ordres :
  voir                      ce que l'habitant voit (type, angle, distance)
  etat                      position estimée, posture, zone, heure
  aller REF [dist]          marcher jusqu'à REF (ex: aller campfire 2, aller bench1, aller d-h7)
  asseoir [REF]             s'asseoir sur un banc      | lever   se lever
  entrer MAISON             entrer (ex: entrer h5)     | sortir MAISON   ressortir
  dormir                    dormir dans le lit proche  | rentrer   retour maison (transport 10 s)
  panneau                   lire le panneau            | ecrire TEXTE   écrire sur le panneau
  dire TEXTE                parler (say)               | geste dance|fear|shrug|point
  tourner DEG               pivoter                    | marcher [walk|sneak|run] DEG   | stop
  tour                      tour d'horizon             | carte    repères connus
  pierre                    aller à la pierre et se transformer (loup, 22h-6h)
  quitter"""


def vis(st):
    return "\n".join(f"  {v['ref']:<22}{v['kind']:<10}angle {v['bearing_deg']:6.0f}°  dist {v['distance_m']:5.1f} m"
                     for v in sorted(st.visible.values(), key=lambda v: v["distance_m"]))


async def main():
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="   [log] %(message)s")
    st = GameState(WorldMap(ROOT / "data" / "village_map.json"))
    raw = open(ROOT / "logs" / f"cockpit-{int(time.time())}.raw.jsonl", "w", buffering=1)
    s = Session(os.environ["GAME_WS_URL"], os.environ["TEAM_TOKEN"], "cockpit-1", st, log=raw)
    b = Body(s)
    net = asyncio.create_task(s.run())
    async def drain():
        while True:
            f = await s.events.get()
            if f["type"] in ("sound", "game_event", "decision_request"):
                print(f"   [évènement] {f['type']} {str(f['data'])[:200]}")
    asyncio.create_task(drain())
    while not st.alive:
        await st.wait_change(0.5)
    print(f"Connecté : {st.me.get('name')} (maison {st.me.get('home')}). Tape `aide`.")
    loop = asyncio.get_running_loop()
    while True:
        line = (await loop.run_in_executor(None, input, "\n> ")).strip().split()
        if not line:
            continue
        c, a = line[0], line[1:]
        t0 = time.time()
        try:
            if c in ("quitter", "q"): break
            elif c == "aide": print(AIDE)
            elif c == "voir": print(vis(st))
            elif c == "etat":
                st.world.advance(); w = st.world
                print(f"  pos=({w.pose[0]:.1f},{w.pose[1]:.1f}) cap={w.pose[2]:.0f}° fixe={w.fixed} posture={st.posture} "
                      f"zones={st.zones} heure={st.hour() and round(st.hour(), 1)} forme={st.form} rôle={st.role}")
            elif c == "aller": print("  ->", "ARRIVÉ" if await b.goto(a[0], stop=float(a[1]) if len(a) > 1 else 1.5) else "ÉCHEC")
            elif c == "asseoir": print("  ->", await b.sit(a[0] if a else None))
            elif c == "lever": print("  ->", await b.stand())
            elif c == "entrer": print("  ->", "DEDANS" if await b.enter(a[0]) else "ÉCHEC")
            elif c == "sortir": print("  ->", "DEHORS" if await b.leave(a[0]) else "ÉCHEC")
            elif c == "dormir": print("  ->", await b.sleep())
            elif c == "rentrer": print("  ->", await b.go_home())
            elif c == "panneau": print("  ->", await b.read_board())
            elif c == "ecrire": print("  ->", await b.write_board(" ".join(a)))
            elif c == "dire": print("  ->", await b.speak(" ".join(a)))
            elif c == "geste": print("  ->", await b.emote(a[0]))
            elif c == "tourner": print("  ->", await b.turn(float(a[0])))
            elif c == "marcher": print("  ->", await b.move(a[0] if a[0] in ("walk", "sneak", "run") else "walk", float(a[-1]) if a[-1].lstrip('-').isdigit() else 0))
            elif c == "stop": print("  ->", await b.stop())
            elif c == "tour": await b.scan_around(); print(vis(st))
            elif c == "carte": print({k: (round(v['x']), round(v['y']), v['kind']) for k, v in st.world.landmarks.items()})
            elif c == "pierre": print("  ->", await b.transform())
            else: print("  ordre inconnu, tape `aide`")
        except Exception as e:
            print("  ERREUR :", repr(e))
        print(f"  ({time.time() - t0:.1f}s)")
    await b.stop()
    st.world.save(force=st.world.fixed)
    net.cancel()


asyncio.run(main())
