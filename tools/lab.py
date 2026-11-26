"""Laboratoire d'expériences : session brute avec trace horodatée de tout ce qui arrive."""
import asyncio, json, os, time, uuid
from pathlib import Path
from dotenv import load_dotenv
from websockets.asyncio.client import connect

ROOT = Path(__file__).parent.parent

class Lab:
    def __init__(self, name="lab-1"):
        self.name = name
        self.trace = []          # (t_recv, frame)
        self.visible = {}        # ref -> dernière observation
        self.self_ = {}
        self.scan = None
        self.results = {}        # command_id -> data
        self.waiters = {}
        self.ws = None

    async def __aenter__(self):
        load_dotenv(ROOT / ".env")
        self.cm = connect(os.environ["GAME_WS_URL"],
            additional_headers={"Authorization": "Bearer " + os.environ["TEAM_TOKEN"]}, max_size=2**20)
        self.ws = await self.cm.__aenter__()
        await self.ws.send(json.dumps({"type": "hello", "agent_version": self.name}))
        self.task = asyncio.create_task(self._read())
        await asyncio.sleep(0.6)
        return self

    async def __aexit__(self, *a):
        self.task.cancel()
        out = ROOT / "logs" / f"lab-{int(time.time())}.jsonl"
        with out.open("w") as f:
            for t, fr in self.trace:
                f.write(json.dumps({"t": t, **fr}) + "\n")
        print("trace:", out)
        await self.cm.__aexit__(*a)

    async def _read(self):
        async for m in self.ws:
            f = json.loads(m); t = time.time()
            self.trace.append((t, f))
            d = f["data"]
            if f["type"] == "snapshot":
                self.self_ = d.get("self", {}); self.scan = d.get("scan")
                self.visible = {v["ref"]: v for v in d.get("visible", [])}
            elif f["type"] == "vision":
                for v in d["entered"] + d["updated"]: self.visible[v["ref"]] = v
                for r in d["left"]: self.visible.pop(r, None)
            elif f["type"] == "self": self.self_ = d
            elif f["type"] == "scan": self.scan = d
            elif f["type"] == "command_result":
                self.results[d["command_id"]] = d
                w = self.waiters.pop(d["command_id"], None)
                if w: w.set()

    async def send(self, kind, data, wait=True, timeout=5):
        cid = uuid.uuid4().hex[:8]
        ev = asyncio.Event(); self.waiters[cid] = ev
        await self.ws.send(json.dumps({"type": kind, "command_id": cid, "data": data}))
        if wait:
            try: await asyncio.wait_for(ev.wait(), timeout)
            except asyncio.TimeoutError: return {"ok": None, "code": "timeout"}
            return self.results[cid]
        return cid

    def sample(self, ref):
        v = self.visible.get(ref)
        return (round(time.time(), 3), None if not v else (round(v["bearing_deg"], 2), round(v["distance_m"], 2)))
