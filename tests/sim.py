"""Simulateur local du serveur de jeu (sous-ensemble fidèle du protocole), pour tester l'agent hors ligne.

Monde 2D : maisons carrées avec une ouverture de porte, bancs, feu, panneau, pierre, passants immobiles.
Le joueur est un disque. Vision : cône de ±60°, portée 22 m de jour / 8 m de nuit (16 m pour un loup),
occultation par les murs. Balayage : 30 secteurs de 4°. Angles : 0 = devant, +90 = droite.
"""
import asyncio
import json
import math
import time

from websockets.asyncio.server import serve

PLAYER_R = 0.3
SPEEDS = {"sneak": 0.83, "walk": 1.81, "run": 3.6}


def seg_ray(ox, oy, dx, dy, ax, ay, bx, by):
    """Distance le long du rayon (ox,oy)+t(dx,dy) jusqu'au segment AB, ou None."""
    ex, ey = bx - ax, by - ay
    den = dx * ey - dy * ex
    if abs(den) < 1e-9:
        return None
    t = ((ax - ox) * ey - (ay - oy) * ex) / den
    u = ((ax - ox) * dy - (ay - oy) * dx) / den
    return t if t >= 0 and 0 <= u <= 1 else None


def circle_ray(ox, oy, dx, dy, cx, cy, r):
    fx, fy = ox - cx, oy - cy
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - r * r
    disc = b * b - c
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t >= 0 else None


def seg_dist(px, py, ax, ay, bx, by):
    ex, ey = bx - ax, by - ay
    L = ex * ex + ey * ey
    u = 0 if L == 0 else max(0, min(1, ((px - ax) * ex + (py - ay) * ey) / L))
    return math.hypot(px - (ax + u * ex), py - (ay + u * ey))


class House:
    HALF = 1.9
    DOOR = 0.5   # demi-largeur de l'ouverture

    def __init__(self, n, cx, cy, side="S"):
        self.n, self.cx, self.cy, self.side = n, cx, cy, side
        h = self.HALF
        corners = {"N": ((-h, h), (h, h)), "E": ((h, h), (h, -h)), "S": ((h, -h), (-h, -h)), "W": ((-h, -h), (-h, h))}
        self.segs = []
        for s, (a, b) in corners.items():
            ax, ay, bx, by = cx + a[0], cy + a[1], cx + b[0], cy + b[1]
            if s == side:
                mx, my = (ax + bx) / 2, (ay + by) / 2
                L = math.hypot(bx - ax, by - ay)
                ux, uy = (bx - ax) / L, (by - ay) / L
                self.segs.append((ax, ay, mx - ux * self.DOOR, my - uy * self.DOOR))
                self.segs.append((mx + ux * self.DOOR, my + uy * self.DOOR, bx, by))
                nx = {"N": 0, "E": 1, "S": 0, "W": -1}[s]
                ny = {"N": 1, "E": 0, "S": -1, "W": 0}[s]
                self.door = (mx, my)
            else:
                self.segs.append((ax, ay, bx, by))
        self.bed = (cx - 0.6, cy + 0.6)


class Sim:
    def __init__(self, role="villager", minute=1380, start=(0.0, -12.0), heading=0.0, cycle_ms=10 ** 9):
        self.houses = [House(4, 14, 8, "W"), House(5, -10, 6, "S"), House(6, 12, -4, "N"), House(7, -14, -8, "E")]
        self.static = {"campfire": (0.0, 0.0), "board": (4.0, -3.0), "stone": (0.0, 28.0), "canteen": (18.0, 14.0)}
        self.benches = {f"bench{i+1}": p for i, p in enumerate([(-3, -2), (3, 2.5), (-2.5, 3), (4, -0.5)])}
        self.persons = {"p1": ("Léa", (6.0, -11.0)), "p2": ("Basile", (-5.0, 18.0)), "p3": ("Émile", (-12.5, 6.8))}
        self.role, self.minute, self.cycle_ms = role, minute, cycle_ms   # cycle_ms énorme : horloge figée dans les tests
        self.x, self.y, self.heading = start[0], start[1], heading
        self.gait, self.bearing, self.posture, self.form = "stop", 0.0, "standing", "human"
        self.blocked = False
        self.home = 5
        self.kills = []
        self.board = []
        self.return_at = None
        self.known = {}
        self.seen = {}
        self.log = []
        self.ws = None
        self.round = {"round_id": "r1", "mode": "trial", "day": 1}
        self.requests = {}          # request_id -> demande ouverte
        self.responses = []         # (request_id, action, data) acceptées
        self.refusals = []          # (action, code)
        self.spoken = []            # paroles émises par l'agent
        self.muted = False
        self.dead = False
        self.last_speak = 0.0
        self.clock_speed = 0.0      # minutes de jeu par seconde réelle (0 = horloge figée)
        self.challenge_pt = (18.0, 14.0)
        self.person_posture = {}

    # ---- géométrie
    def obstacles(self):
        segs = [s for h in self.houses for s in h.segs]
        circles = [(p[0], p[1], 0.55, "prop") for p in self.benches.values()]
        circles.append((0.0, 0.0, 0.5, "prop"))
        circles += [(pos[0], pos[1], 0.3, "body") for _, pos in self.persons.values()]
        circles.append((self.static["stone"][0], self.static["stone"][1], 0.6, "prop"))
        return segs, circles

    def collides(self, x, y):
        segs, circles = self.obstacles()
        if any(seg_dist(x, y, *s) < PLAYER_R for s in segs):
            return True
        return any(math.hypot(x - c[0], y - c[1]) < c[2] + PLAYER_R and c[3] != "body" or
                   (c[3] == "body" and math.hypot(x - c[0], y - c[1]) < c[2] + PLAYER_R) for c in circles)

    def ray(self, a_deg, rng):
        r = math.radians(self.heading + a_deg)
        dx, dy = math.sin(r), math.cos(r)
        segs, circles = self.obstacles()
        best, kind = None, None
        for s in segs:
            t = seg_ray(self.x, self.y, dx, dy, *s)
            if t is not None and (best is None or t < best):
                best, kind = t, "wall"
        for cx, cy, rad, k in circles:
            t = circle_ray(self.x, self.y, dx, dy, cx, cy, rad)
            if t is not None and (best is None or t < best):
                best, kind = t, k
        return (best, kind) if best is not None and best <= rng else (None, None)

    def vrange(self):
        h = self.minute / 60
        night = h >= 22 or h < 8
        return (16.0 if self.form == "wolf" else 8.0) if night else 22.0

    def visible_now(self):
        out = {}
        rng = self.vrange()

        def add(ref, kind, pos, **extra):
            dx, dy = pos[0] - self.x, pos[1] - self.y
            d = math.hypot(dx, dy)
            b = (math.degrees(math.atan2(dx, dy)) - self.heading + 180) % 360 - 180
            if d > rng or abs(b) > 60:
                return
            # occultation : le rayon vers l'objet doit arriver avant tout mur
            t, k = self.ray_to(pos)
            if t is not None and t < d - 0.8:
                return
            out[ref] = {"ref": ref, "kind": kind, "bearing_deg": b, "distance_m": d, **extra}

        for h in self.houses:
            add(f"h{h.n}", "house", (h.cx, h.cy), name=f"Maison nº {h.n}")
            add(f"d-h{h.n}", "door", h.door, of=f"h{h.n}")
            add(f"bed-h{h.n}", "bed", h.bed)
        for ref, p in self.benches.items():
            add(ref, "bench", p)
        for ref, p in self.static.items():
            add(ref, ref, p)
        for ref, (name, p) in self.persons.items():
            add(ref, "person", p, name=name, posture=self.person_posture.get(ref, "standing"), engaged=True)
        return out

    def ray_to(self, pos):
        dx, dy = pos[0] - self.x, pos[1] - self.y
        d = math.hypot(dx, dy) or 1
        segs, _ = self.obstacles()
        best = None
        for s in segs:
            t = seg_ray(self.x, self.y, dx / d, dy / d, *s)
            if t is not None and (best is None or t < best):
                best = t
        return best, "wall"

    def scan_now(self):
        rng = self.vrange()
        ds, ks = [], []
        for i in range(30):
            d, k = self.ray(-60 + (i + 0.5) * 4, rng)
            ds.append(None if d is None else round(d, 2))
            ks.append(k)
        return {"from_deg": -60.0, "step_deg": 4.0, "range_m": rng, "distances_m": ds, "kinds": ks}

    # ---- zones / état
    def zones(self):
        z = []
        if math.hypot(self.x, self.y) < 6:
            z.append("council")
        h = next(h for h in self.houses if h.n == self.home)
        if abs(self.x - h.cx) < h.HALF and abs(self.y - h.cy) < h.HALF:
            z.append("home")
        if math.hypot(self.x - self.challenge_pt[0], self.y - self.challenge_pt[1]) < 6:
            z.append("challenge")
        return z

    def self_msg(self):
        return {"name": "Cédric", "engaged": True, "gait": self.gait, "posture": self.posture, "home": f"Maison nº {self.home}",
                "zones": self.zones(), "role": self.role, "form": self.form, "captain": False,
                "powers": ({"home_return_at_ms": self.return_at} if self.return_at else {}),
                "night_sleep_h": 0, "fatigue": 0.0, "noise_emitted": 0, "noise_heard": 0,
                "motion_reason": "blocked" if self.blocked else None}

    def snapshot(self):
        return {"status": "alive", "self": self.self_msg(), "clock": {"day": 1, "minute": self.minute, "cycle_ms": self.cycle_ms},
                "round": self.round, "visible": list(self.visible_now().values()), "scan": self.scan_now(), "requests": []}

    # ---- pilotage par les tests : événements, invitations, sons
    async def emit(self, kind, **data):
        await self.send("game_event", {"kind": kind, **data})

    async def open_request(self, kind, actions, seconds=30, prompt=None, allow_abstain=False):
        rid = f"{kind}-{len(self.requests) + len(self.responses) + 1}"
        d = {"request_id": rid, "kind": kind, "deadline_ms": int(time.time() * 1000 + seconds * 1000),
             "allow_abstain": allow_abstain, "actions": actions}
        if prompt:
            d["prompt"] = prompt
        self.requests[rid] = d
        await self.send("decision_request", d)
        return rid

    async def npc_say(self, name, text, sector="front", volume="say", speaker_ref=None):
        d = {"kind": "speech", "volume": volume, "sector": sector, "text": text}
        if speaker_ref:
            d.update(speaker_ref=speaker_ref, speaker_name=name)
        await self.send("sound", d)

    async def kill_player(self):
        self.dead = True
        self.gait = "stop"
        await self.send("snapshot", {"status": "dead", "requests": []})

    # ---- simulation
    async def send(self, kind, data):
        self.seq += 1
        await self.ws.send(json.dumps({"type": kind, "seq": self.seq, "time_ms": int(time.time() * 1000), "data": data}))

    async def result(self, cid, ok, code=None, value=None):
        d = {"command_id": cid, "ok": ok}
        if ok:
            d["value"] = value or {}
        else:
            d["code"] = code
        await self.send("command_result", d)

    def adjacent(self, ref, reach=2.0):
        v = self.visible_now().get(ref)
        return v if v and v["distance_m"] <= reach else None

    async def refuse(self, cid, action, code):
        self.refusals.append((action, code))
        await self.result(cid, False, code)

    async def respond(self, cid, a, d):
        rq = self.requests.get(d.get("request_id"))
        if not rq or time.time() * 1000 > rq["deadline_ms"]:
            return await self.refuse(cid, a, "request_closed")
        offered = {x["action"]: x for x in rq["actions"]}
        if a == "abstain":
            if not rq["allow_abstain"]:
                return await self.refuse(cid, a, "action_unavailable")
        elif a not in offered:
            return await self.refuse(cid, a, "action_unavailable")
        if a == "vote" and "council" not in self.zones():
            return await self.refuse(cid, a, "outside_council")
        if a == "answer_challenge" and "challenge" not in self.zones():
            return await self.refuse(cid, a, "outside_challenge")
        if a in ("inspect", "heal", "poison") and "home" not in self.zones():
            return await self.refuse(cid, a, "outside_home")
        if a in ("vote", "inspect", "heal", "poison", "name_successor"):
            if d.get("choice_id") not in [c["choice_id"] for c in offered[a].get("choices", [])]:
                return await self.refuse(cid, a, "invalid_payload")
        self.requests.pop(rq["request_id"])
        self.responses.append((rq["request_id"], a, d))
        await self.result(cid, True, value={"role": "wolf"} if a == "inspect" else None)

    async def act(self, cid, d):
        a = d["action"]
        ref = d.get("target_ref")
        if self.dead and a not in ("vote", "heal", "poison", "name_successor", "abstain"):
            return await self.refuse(cid, a, "dead")
        if a in ("vote", "inspect", "heal", "poison", "name_successor", "answer_challenge", "abstain"):
            return await self.respond(cid, a, d)
        if a in ("sit", "sleep", "read_board", "write_board", "transform", "attack"):
            v = self.adjacent(ref) if ref else None
            if not v:
                return await self.result(cid, False, "out_of_reach")
        if a == "sit":
            if v["kind"] != "bench":
                return await self.result(cid, False, "out_of_reach")
            self.posture = "sitting"
            self.heading = (self.heading + 37.0) % 360       # s'asseoir tourne l'habitant vers le banc d'un angle que l'agent ignore
        elif a == "sleep":
            if v["kind"] != "bed":
                return await self.result(cid, False, "out_of_reach")
            self.posture = "sleeping"
        elif a == "stand":
            self.posture = "standing"
        elif a == "read_board":
            return await self.result(cid, True, value={"entries": list(self.board)})
        elif a == "write_board":
            self.board.append({"time_ms": int(time.time() * 1000), "text": d["text"]})
        elif a == "transform":
            h = self.minute / 60
            if self.role != "wolf" or not (h >= 22 or h < 6) or v["kind"] != "stone" or self.form == "wolf":
                return await self.result(cid, False, "action_unavailable")
            self.form = "wolf"
        elif a == "attack":
            if self.form != "wolf" or d.get("round_id") != self.round["round_id"] or v["kind"] != "person":
                return await self.result(cid, False, "action_unavailable")
            self.kills.append(ref)
            self.persons.pop(ref)
            if any(abs(self.x - h.cx) < h.HALF and abs(self.y - h.cy) < h.HALF for h in self.houses):
                self.form = "human"      # elle tue dans une maison : sa chasse est finie
        elif a == "return_home":
            if self.return_at:
                return await self.result(cid, False, "rate_limited")
            self.gait = "stop"
            self.return_at = int(time.time() * 1000) + 10000
            await self.send("self", self.self_msg())
            return await self.result(cid, True, value={"home_return_at_ms": self.return_at})
        else:
            return await self.result(cid, False, "unknown_command")
        await self.result(cid, True)
        await self.send("self", self.self_msg())

    async def handle(self, msg):
        t, cid, d = msg["type"], msg["command_id"], msg["data"]
        self.log.append(msg)
        if self.posture != "standing" and (t == "move" and d.get("gait") != "stop"):
            return await self.result(cid, False, "action_unavailable")
        if t == "move":
            if d["gait"] == "stop":
                self.gait = "stop"
            else:
                self.gait, self.bearing = d["gait"], d.get("bearing_deg", 0.0)
                self.return_at = None
            self.blocked = False
            await self.result(cid, True)
            await self.send("self", self.self_msg())
        elif t == "turn":
            self.heading = (self.heading + d["angle_deg"]) % 360
            await self.result(cid, True)
        elif t == "speak":
            now = time.time()
            if self.muted:
                return await self.refuse(cid, "speak", "muted")
            if not 1 <= len(d.get("text", "")) <= 240 or d.get("volume") not in ("whisper", "say", "shout"):
                return await self.refuse(cid, "speak", "invalid_payload")
            if now - self.last_speak < 2.0:
                return await self.refuse(cid, "speak", "rate_limited")
            self.last_speak = now
            self.spoken.append((self.minute, d["volume"], d["text"]))
            await self.result(cid, True)
        elif t == "emote":
            await self.result(cid, True)
        elif t == "act":
            await self.act(cid, d)

    async def loop(self):
        dt = 0.03
        prev = {}
        last_scan = None
        while True:
            await asyncio.sleep(dt)
            if self.clock_speed:
                old = self.minute
                self.minute = (self.minute + dt * self.clock_speed) % 1440
                for step, at in (("nightfall", 1320), ("village_wakes", 480)):
                    crossed = (old < at <= self.minute) if old <= self.minute else (old < at or at <= self.minute)
                    if crossed:
                        await self.emit("scheduled_step", step=step, place="campfire", text=step)
            if self.return_at and time.time() * 1000 >= self.return_at:
                h = next(h for h in self.houses if h.n == self.home)
                self.x, self.y = h.cx, h.cy               # le serveur pose l'habitant au centre de sa maison
                bx, by = h.bed[0] - self.x, h.bed[1] - self.y
                self.heading = math.degrees(math.atan2(bx, by))
                self.return_at = None
                await self.send("self", self.self_msg())
            if self.gait != "stop" and self.posture == "standing":
                r = math.radians(self.heading + self.bearing)
                step = SPEEDS[self.gait] * dt
                nx, ny = self.x + math.sin(r) * step, self.y + math.cos(r) * step
                if self.collides(nx, ny):
                    self.gait, self.blocked = "stop", True
                    await self.send("self", self.self_msg())
                else:
                    self.x, self.y = nx, ny
            cur = self.visible_now() if self.posture != "sleeping" else {}
            ent = [v for r, v in cur.items() if r not in prev]
            upd = [v for r, v in cur.items() if r in prev and (abs(v["bearing_deg"] - prev[r]["bearing_deg"]) > 1e-6 or abs(v["distance_m"] - prev[r]["distance_m"]) > 1e-6)]
            left = [r for r in prev if r not in cur]
            if ent or upd or left:
                await self.send("vision", {"entered": ent, "updated": upd, "left": left})
                sc = self.scan_now()
                if sc != last_scan:
                    await self.send("scan", sc)
                    last_scan = sc
            prev = cur

    async def serve(self, ws):
        self.ws, self.seq = ws, 0
        await ws.recv()  # hello
        await self.send("snapshot", self.snapshot())
        task = asyncio.create_task(self.loop())
        try:
            async for raw in ws:
                await self.handle(json.loads(raw))
        finally:
            task.cancel()

    async def start(self, port=0):
        self.server = await serve(self.serve, "127.0.0.1", port)
        self.port = self.server.sockets[0].getsockname()[1]
        return f"ws://127.0.0.1:{self.port}"

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()
