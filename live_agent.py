"""Agent en direct : explore et cartographie le village, rentre la nuit, vote au conseil, et ENREGISTRE TOUT.
Lancer : .venv/bin/python live_agent.py      (Ctrl-C pour arrêter)
Logs : logs/live-<ts>.raw.jsonl (tous les messages bruts) et logs/live-<ts>.events.log (lisible).
Carte partagée : data/village_map.json"""
import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv

import journal
from graphe import Graphe

from village.body import Body
from village.net import Fatal, Session
from village.state import GameState
from village.worldmap import WorldMap

ROOT = Path(__file__).parent
ts = int(time.time())
(ROOT / "logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                    handlers=[logging.FileHandler(ROOT / "logs" / f"live-{ts}.events.log"), logging.StreamHandler()])
log = logging.getLogger("live")


async def events(s, body):
    """Consomme les événements du serveur : journalise tout, répond aux invitations."""
    while True:
        f = await s.events.get()
        journal.handled(f)
        k, d = f["type"], f["data"]
        if k in ("sound", "game_event", "gesture", "decision_request", "decision_closed", "snapshot"):
            log.info("EVT %s %s", k, json.dumps(d, ensure_ascii=False)[:400])
        if k == "decision_request":
            asyncio.create_task(answer(s, body, d))


async def answer(s, body, req):
    """Invitation : va au conseil si besoin et répond (vote local, sans modèle)."""
    for a in req.get("actions", []):
        if a["action"] == "vote" and a.get("choices"):
            for _ in range(3):
                if "council" not in s.state.zones:
                    await body.goto("campfire", stop=3.0, timeout=25)
                res = await body.respond(req["request_id"], "vote", choice_id=random.choice(a["choices"])["choice_id"])
                log.info("VOTE -> %s", res)
                if res.get("ok") or res.get("code") != "outside_council":
                    return


async def status(s):
    st = s.state
    while True:
        await asyncio.sleep(5)
        w = st.world
        w.advance()
        vis = {}
        for v in st.visible.values():
            vis[v["kind"]] = vis.get(v["kind"], 0) + 1
        log.info("STATUS pos=(%.1f,%.1f,%.0f) fixe=%s posture=%s gait=%s zones=%s heure=%s role=%s form=%s vis=%s lm=%d",
                 *w.pose, w.fixed, st.posture, st.gait, st.zones, st.hour() and round(st.hour(), 1), st.role, st.form, vis, len(w.landmarks))
        w.save(force=w.fixed)


async def behave(s, body):
    st = s.state
    while not st.alive:
        await st.wait_change(1.0)
    log.info("Habitant : %s, maison %s", st.me.get("name"), st.me.get("home"))
    while True:
        try:
            h = st.hour()
            night = h is not None and (h >= 22 or h < 6)
            if not st.alive:
                await st.wait_change(1.0)
            elif st.posture == "sleeping":
                if not night:
                    await body.stand()
                await asyncio.sleep(1)
            elif night:
                if "home" not in st.zones:
                    log.info("NUIT -> return_home : %s", await body.go_home())
                if "home" in st.zones:
                    log.info("NUIT -> sleep : %s", (await body.sleep()).get("code"))
                await asyncio.sleep(2)
            else:
                if st.posture == "sitting":
                    await body.stand()
                await body.explore(budget=20)
        except Exception:
            log.exception("erreur de comportement")
            await asyncio.sleep(1)


async def observabilite(st):
    """Écrit régulièrement l'état de l'agent dans le journal, et le graphe à côté du journal."""
    graphe = Graphe()
    journal.subscribe(graphe.observe)
    while True:
        await asyncio.sleep(15)
        journal.state(name=st.me.get("name"), role=st.role, posture=st.posture, zones=st.zones,
                      alive=st.alive, connected=st.connected, open_requests=sorted(st.requests))
        if journal.ENABLED:
            try:
                graphe.ecrire_json(journal.path().with_suffix(".graphe.json"))
            except OSError:
                pass


async def main():
    load_dotenv(ROOT / ".env")
    st = GameState(WorldMap(ROOT / "data" / "village_map.json"))
    raw = open(ROOT / "logs" / f"live-{ts}.raw.jsonl", "w", buffering=1)
    s = Session(os.environ["GAME_WS_URL"], os.environ["TEAM_TOKEN"], "live-1", st, log=raw)
    body = Body(s)
    journal.session("start", agent_version="live-1", trace=str(journal.path()))
    print("Journal :", journal.path(), flush=True)
    tasks = [asyncio.create_task(c) for c in (s.run(), events(s, body), status(s), behave(s, body), observabilite(st))]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            t.result()
    except (Fatal, KeyboardInterrupt) as e:
        log.info("Arrêt : %s", e)
    finally:
        await body.stop()
        st.world.save(force=st.world.fixed)


asyncio.run(main())
