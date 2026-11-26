"""Agent autonome piloté par un modèle. Lancer :
    .venv/bin/python run_agent.py [--model MODELE] [--max-appels 300] [--persona data/persona.txt]
Logs : logs/agent-*.jsonl (chaque décision : contexte, réponse brute, action, résultat, coût), logs/agent-*.log, logs/agent-*.raw.jsonl (réseau).
Mémoire : data/memory.json — Carte : data/village_map.json."""
import argparse
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from village.body import Body
from village.brain import Brain
from village.llm import LLM
from village.net import Fatal, Session
from village.state import GameState
from village.worldmap import WorldMap

ROOT = Path(__file__).parent


def usage():
    req = Request(os.environ["LLM_GATEWAY_URL"] + "/usage", headers={"Authorization": "Bearer " + os.environ["TEAM_TOKEN"]})
    with urlopen(req, timeout=8) as r:
        return json.load(r)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model")
    p.add_argument("--max-appels", type=int, default=300)
    p.add_argument("--persona", default=str(ROOT / "data" / "persona.txt"))
    p.add_argument("--url", help="URL WebSocket (défaut : GAME_WS_URL du .env)")
    a = p.parse_args()
    load_dotenv(ROOT / ".env")
    ts = int(time.time())
    (ROOT / "logs").mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.FileHandler(ROOT / "logs" / f"agent-{ts}.log"), logging.StreamHandler()])
    st = GameState(WorldMap(ROOT / "data" / "village_map.json"))
    raw = open(ROOT / "logs" / f"agent-{ts}.raw.jsonl", "w", buffering=1)
    s = Session(a.url or os.environ["GAME_WS_URL"], os.environ["TEAM_TOKEN"], "brain-1", st, log=raw)
    body, llm = Body(s), LLM(a.model)
    brain = Brain(s, body, llm, Path(a.persona).read_text().strip(), ROOT / "data", ROOT / "logs", a.max_appels)

    async def saver():
        while True:
            await asyncio.sleep(5)
            st.world.advance()
            st.world.save(force=st.world.fixed)
    tasks = [asyncio.create_task(c) for c in (s.run(), brain.run(), saver())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in done:
            t.result()
    except (Fatal, KeyboardInterrupt) as e:
        logging.info("Arrêt : %s", e)
    finally:
        await body.stop()
        st.world.save(force=st.world.fixed)
        logging.info("Appels modèle: %d, coût: %.5f $, jetons: %d in / %d out", llm.calls, llm.cost, llm.tokens_in, llm.tokens_out)

asyncio.run(main())
