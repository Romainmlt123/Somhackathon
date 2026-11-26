"""Sonde : se connecte, envoie hello, journalise tous les messages bruts (JSONL), puis se déconnecte."""
import asyncio, json, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from websockets.asyncio.client import connect

async def main(seconds):
    load_dotenv(Path(__file__).parent.parent / ".env")
    log = Path(__file__).parent.parent / "logs" / f"probe-{int(time.time())}.jsonl"
    async with connect(os.environ["GAME_WS_URL"],
                       additional_headers={"Authorization": "Bearer " + os.environ["TEAM_TOKEN"]},
                       max_size=2**20) as ws:
        await ws.send(json.dumps({"type": "hello", "agent_version": "probe-1"}))
        end = time.time() + seconds
        with log.open("w") as f:
            while time.time() < end:
                try:
                    m = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
                except asyncio.TimeoutError:
                    break
                f.write(m + "\n")
                d = json.loads(m)
                print(d["type"], json.dumps(d["data"], ensure_ascii=False)[:300])
    print("log:", log)

asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 5))
