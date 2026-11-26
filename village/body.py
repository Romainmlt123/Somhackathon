"""Le corps de l'habitant : toutes les actions du jeu sous forme de coroutines fiables.

    body = Body(session)
    await body.goto("campfire", stop=2.0)       # navigation réactive guidée par le scan
    await body.sit("bench4")                    # s'approche, se tourne, s'assoit
    await body.enter("h7")                      # trouve la porte, entre dans la maison
    await body.transform()                      # loup : va à la pierre et se transforme
    await body.attack(ref)                      # loup : s'approche à portée et attaque
"""
import asyncio
import logging
import math
import random
import time

from .geometry import local_to_world, norm, polar_to_local, world_to_polar
from .grid import ZONE, ray
from .grid import cell as grid_cell

log = logging.getLogger("village.body")

BODY_HALF = 0.45        # demi-largeur de sécurité du couloir de marche, en mètres
REACH = 2.0             # portée d'interaction (banc, lit, pierre, attaque) annoncée par les règles


class Blocked(Exception):
    pass


def sector_clearance(scan, a):
    """Distance libre dans la direction `a` (degrés, repère de l'habitant) d'après le balayage."""
    if not scan:
        return 0.0
    start, step, rng = scan["from_deg"], scan["step_deg"], scan["range_m"]
    best = rng
    for i, d in enumerate(scan["distances_m"]):
        if d is None:
            continue
        aj = start + (i + 0.5) * step
        diff = abs(norm(aj - a))
        if diff >= 90:
            continue
        lateral = d * math.sin(math.radians(diff))
        if lateral <= BODY_HALF:
            best = min(best, d * math.cos(math.radians(diff)))
    return best


class Body:
    def __init__(self, session):
        self.s = session
        self.st = session.state
        self.w = self.st.world
        self.last_move = None       # (gait, bearing) dernier ordre de marche envoyé
        self.last_dir = 0.0

    # ------------------------------------------------------------ commandes brutes
    async def _act(self, action, **kw):
        res = await self.s.send("act", {"action": action, **kw})
        if not res.get("ok"):
            log.info("act %s %s -> %s", action, kw, res.get("code"))
        return res

    async def move(self, gait="walk", bearing=0.0):
        if self.last_move == (gait, round(bearing)) and self.st.gait == gait:
            return {"ok": True}
        self.last_move = (gait, round(bearing))
        self.last_dir = norm(self.w.pose[2] + bearing)      # direction absolue du dernier ordre de marche
        self.w.set_motion(gait, bearing)
        return await self.s.send("move", {"gait": gait, "bearing_deg": float(bearing)})

    async def stop(self):
        self.last_move = None
        self.w.set_motion("stop")
        return await self.s.send("move", {"gait": "stop"})

    async def turn(self, angle):
        """Pivote de `angle` degrés (instantané côté serveur)."""
        if abs(angle) < 0.5:
            return {"ok": True}
        angle = float(norm(angle))
        if angle >= 180:
            angle = -180.0                  # le protocole exclut +180
        self.w.turn_sent(angle)          # le cap suit l'ordre ; les perceptions sont ignorées jusqu'à l'accusé
        self.last_move = None            # un pivot change le sens du « bearing » relatif : on réémettra le prochain move
        res = await self.s.send("turn", {"angle_deg": angle})
        self.w.turn_done(res.get("ok") if res.get("ok") is not None else True, angle)
        return res

    async def speak(self, text, volume="say"):
        return await self.s.send("speak", {"volume": volume, "text": text[:240]})

    async def emote(self, gesture, target_ref=None, bearing=None):
        d = {"gesture": gesture}
        if gesture == "point":
            if target_ref:
                d["target_ref"] = target_ref
            elif bearing is not None:
                d["bearing_deg"] = float(bearing)
        return await self.s.send("emote", d)

    async def stand(self):
        res = await self._act("stand")
        await self._wait(lambda: self.st.posture == "standing", 2.0)
        return res

    async def return_home(self):
        return await self._act("return_home")

    def home_ref(self):
        """Référence de notre maison (« Maison nº 5 » -> « h5 »)."""
        import re
        m = re.search(r"(\d+)", self.st.me.get("home") or "")
        return f"h{m.group(1)}" if m else None

    async def go_home(self, wait=13.0):
        """Retour à la maison par transport (10 s, 1 demande par minute). Retrouve ensuite sa pose à l'intérieur."""
        res = await self.return_home()
        if not res.get("ok"):
            return res
        arrived = await self._wait(lambda: "home" in self.st.zones and "home_return_at_ms" not in self.st.me.get("powers", {}), wait)
        if arrived:
            await self.st.wait_change(0.3)
            if not self.w.fixed:
                await self.localize()
        return {"ok": arrived, "code": None if arrived else "cancelled"}

    async def walk_home(self):
        """Rentre à pied : suppose notre maison déjà cartographiée (ou visible)."""
        h = self.home_ref()
        return bool(h) and await self.enter(h)

    async def respond(self, request_id, action, **kw):
        """Répond à une invitation : vote, inspect, heal, poison, name_successor, abstain, answer_challenge."""
        return await self._act(action, request_id=request_id, **kw)

    # ------------------------------------------------------------ attente
    async def _wait(self, cond, timeout=3.0):
        t0 = time.time()
        while not cond():
            if time.time() - t0 > timeout:
                return False
            await self.st.wait_change(0.1)
        return True

    # ------------------------------------------------------------ cibles
    def locate(self, target):
        """(bearing, distance, source) d'une cible : réf. visible (exacte), sinon carte, sinon None.
        `target` : réf (str), point monde (x, y) ou callable renvoyant l'un des deux."""
        self.w.advance()
        if callable(target):
            target = target()
        if isinstance(target, str):
            v = self.st.visible.get(target)
            if v:
                return v["bearing_deg"], v["distance_m"], "vision"
            if self.w.usable:
                p = self.w.polar_to(target)
                if p:
                    return p[0], p[1], "carte"
            return None
        if target is not None and self.w.usable:
            b, d = world_to_polar(target, self.w.pose)
            return b, d, "carte"
        return None

    def choose_direction(self, goal_b, need):
        """Direction de marche (relative au cap actuel) la plus proche du but avec assez de dégagement."""
        scan = self.st.scan
        if not scan:
            return goal_b, 0.0
        start, step = scan["from_deg"], scan["step_deg"]
        n = len(scan["distances_m"])
        cands = [start + (i + 0.5) * step for i in range(n)] + [goal_b]
        cands = [a for a in cands if start <= a <= start + n * step]
        scored = [(sector_clearance(scan, a), a) for a in cands]
        ok = [(abs(norm(a - goal_b)), a, c) for c, a in scored if c >= need]
        if ok:
            _, a, c = min(ok)
            return a, c
        c, a = max(scored)
        return a, c

    # ------------------------------------------------------------ navigation
    def target_world(self, target, b, d):
        """Point du monde (x, y) de la cible : observation visible (exacte), sinon carte, sinon point donné."""
        if callable(target):
            target = target()
        if isinstance(target, str):
            if target in self.st.visible and self.w.usable:
                return local_to_world(polar_to_local(b, d), self.w.pose)
            return self.w.xy(target)
        return target

    async def goto(self, target, stop=1.5, gait="walk", timeout=40.0, through=0.0):
        """Marche jusqu'à `stop` mètres de la cible. Trajet A* sur la grille d'obstacles, évitement réactif par le scan.
        through > 0 : on vise un passage (porte) et on exige de voir au moins `through` m au-delà. True si arrivé."""
        if self.st.posture in ("sitting", "sleeping"):
            await self.stand()                  # assis ou couché, on ne marche pas
        if not self.w.heading_known:
            await self.localize()               # le cap est perdu (après s'être assis) : tour d'horizon sur deux repères
        grid = self.st.grid
        t0 = time.time()
        stuck_since = None
        last_dist = None
        no_progress_t = time.time()
        path, path_t, path_goal = None, 0.0, None
        while time.time() - t0 < timeout:
            if not self.st.alive or self.st.posture != "standing":
                await self.stop()
                return False
            loc = self.locate(target)
            if loc is None:
                await self.stop()
                return False
            b, d, src = loc
            if d <= stop:
                await self.stop()
                return True
            # trajet : on suit le point le plus lointain atteignable en ligne droite sur le plan A*
            steer_b, dd, final = b, d, True
            tw = self.target_world(target, b, d) if d > 3.0 and self.w.usable and grid.walls else None
            if tw is not None:
                now = time.time()
                if path is None or now - path_t > 0.9 or math.dist(path_goal, tw) > 1.0:
                    grid.forget_heurts(now)
                    path, path_t, path_goal = grid.plan(self.w.pose[:2], tw, tol=max(stop, 0.3)), now, tw
                wp = grid.waypoint(self.w.pose[:2], path)
                if wp is not None:
                    steer_b, dd = world_to_polar(wp, self.w.pose)
                    final = math.dist(wp, tw) < 0.6
            # le but est-il hors du cône de vue ? on pivote (instantané) pour le remettre devant
            if abs(steer_b) > 35:
                await self.turn(steer_b)
                await self.st.wait_change(0.05)
                continue
            need = min(2.5, max(0.8, dd - (stop if final else 0.3))) + (through if final else 0.0)
            a, clear = self.choose_direction(steer_b, need)
            if self.st.me.get("motion_reason") == "blocked" or clear < 0.6:
                stuck_since = stuck_since or time.time()
                if time.time() - stuck_since > 0.35:
                    if self.st.me.get("motion_reason") == "blocked" and self.w.usable:
                        for off in (-40, 0, 40):    # un corps accroche souvent un angle que le rayon central déclare libre
                            px, py, _ = self.w.pose
                            dx, dy = ray(self.last_dir + off, 0.5)
                            grid.mark_heurt((px + dx, py + dy), time.time() + 25)
                    path = None
                    await self.unstick()
                    stuck_since = None
                    continue
            else:
                stuck_since = None
            await self.move(gait, a)
            if last_dist is None or d < last_dist - 0.15:
                last_dist, no_progress_t = d, time.time()
            elif time.time() - no_progress_t > 6.0:
                log.info("goto %s: pas de progrès", target)
                await self.stop()
                return False
            await self.st.wait_change(0.1)
        await self.stop()
        return False

    async def unstick(self):
        """Dégagement quand une collision arrête la marche : pivote à la recherche d'un passage."""
        await self.stop()
        for ang in random.sample([70, -70, 140, -140], 4):
            await self.turn(ang)
            await asyncio.sleep(0.12)
            a, c = self.choose_direction(0.0, 2.5)
            if c >= 1.5:
                await self.move("walk", a)
                await asyncio.sleep(0.8)
                await self.stop()
                return
        await self.move("sneak", 180)
        await asyncio.sleep(0.6)
        await self.stop()

    async def face(self, ref, tol=3.0):
        """Se tourne exactement vers une référence visible."""
        for _ in range(3):
            loc = self.locate(ref)
            if loc is None:
                return False
            if abs(loc[0]) <= tol:
                return True
            await self.turn(loc[0])
            await self.st.wait_change(0.15)
        loc = self.locate(ref)
        return bool(loc and abs(loc[0]) <= tol * 2)

    # ------------------------------------------------------------ interactions
    async def _interact(self, action, ref, reach=REACH, **kw):
        """S'approche à portée de `ref`, le regarde, puis envoie l'action. Gère out_of_reach."""
        for attempt in range(3):
            loc = self.locate(ref)
            if loc is None:
                return {"ok": False, "code": "unseen"}
            if loc[1] > reach - 0.3 or ref not in self.st.visible:
                if not await self.goto(ref, stop=max(0.8, reach - 0.6 - 0.3 * attempt), timeout=30):
                    if ref not in self.st.visible:
                        return {"ok": False, "code": "unreachable"}
            await self.face(ref)
            res = await self._act(action, target_ref=ref, **kw)
            if res.get("ok") or res.get("code") != "out_of_reach":
                return res
        return res

    async def sit(self, ref=None):
        ref = ref or self._nearest_ref("bench")
        res = await self._interact("sit", ref) if ref else {"ok": False, "code": "no_bench"}
        if res.get("ok"):
            self.w.heading_lost()        # s'asseoir tourne l'habitant d'un angle inconnu : le cap sera retrouvé sur 2 repères
            await self._wait(lambda: self.st.posture == "sitting", 2.0)
        return res

    async def sleep(self, ref=None):
        ref = ref or self._nearest_ref("bed")
        res = await self._interact("sleep", ref) if ref else {"ok": False, "code": "no_bed"}
        if res.get("ok"):
            await self._wait(lambda: self.st.posture == "sleeping", 2.0)
        return res

    async def read_board(self, ref=None):
        ref = ref or self._nearest_ref("board")
        res = await self._interact("read_board", ref) if ref else {"ok": False, "code": "no_board"}
        return (res.get("value") or {}).get("entries", []) if res.get("ok") else None

    async def write_board(self, text, ref=None):
        ref = ref or self._nearest_ref("board")
        return await self._interact("write_board", ref, text=text[:240]) if ref else {"ok": False, "code": "no_board"}

    async def transform(self, ref=None):
        """Loup, entre 22 h et 6 h : va à portée de la pierre et se transforme."""
        ref = ref or self._nearest_ref("stone")
        return await self._interact("transform", ref) if ref else {"ok": False, "code": "no_stone"}

    async def attack(self, ref, close=1.4):
        """Loup transformé : se colle à la cible (visible, ≤ 2 m) et attaque."""
        rid = (self.st.round or {}).get("round_id")
        res = await self._interact("attack", ref, reach=REACH - 0.2 if close is None else close + 0.6, round_id=rid)
        return res

    def _nearest_ref(self, kind):
        v = self.st.nearest(kind)
        if v:
            return v["ref"]
        return self.w.nearest(kind) if self.w.usable else None

    # ------------------------------------------------------------ maisons
    async def enter(self, house, timeout=60.0):
        """Va à la porte de `house`, la franchit et s'arrête au centre de la pièce. True si dedans."""
        frame = self.w.door_frame(house)
        door = self.w.door_of(house) or f"d-{house}"
        if frame:
            outside, dp, inside = frame
            if not await self.goto(outside, stop=0.8, timeout=timeout):
                if self.locate(door) is None:
                    return False
        if self.locate(door) is None:
            return False
        await self.face(door)
        # franchit le seuil : on vise la porte en exigeant de voir au-delà (l'ouverture), puis on entre
        if not await self.goto(door, stop=0.35, timeout=20, through=0.6):
            return False
        await self.turn(0)
        await self.move("walk", 0)
        await asyncio.sleep(1.4 / 1.81)
        await self.stop()
        return self.inside(house)

    def inside(self, house, margin=1.6):
        c = self.w.xy(house)
        if not c or not self.w.fixed:
            return False
        return math.dist(self.w.pose[:2], c) < margin

    async def leave(self, house, timeout=30.0):
        """Ressort par la porte de `house`."""
        door = self.w.door_of(house) or f"d-{house}"
        if self.locate(door) is None:
            await self.scan_around()
        if self.locate(door) is None:
            return False
        if not await self.goto(door, stop=0.3, timeout=timeout, through=0.0):
            return False
        await self.move("walk", 0)
        await asyncio.sleep(1.6 / 1.81)
        await self.stop()
        return True

    async def scan_around(self, steps=6):
        """Tour d'horizon : pivote par paliers pour découvrir les repères autour de soi."""
        for _ in range(steps):
            await self.turn(360 / steps)
            await self.st.wait_change(0.2)

    async def localize(self, steps=8):
        """Retrouve sa pose sur la carte : tour d'horizon sur place en notant chaque repère connu avec le
        pivot cumulé (la position ne change pas), puis alignement rigide. True si la pose est retrouvée."""
        from .geometry import polar_to_local, solve_pose
        if self.w.fixed and self.w.heading_known:
            return True
        await self.stop()
        seen = {}                                   # ref -> point local ramené au cap initial
        total = 0.0
        for i in range(steps + 1):
            for o in list(self.st.visible.values()):
                lm = self.w.landmarks.get(o["ref"])
                if lm and o["kind"] in ("house", "door", "bed", "bench", "campfire", "board", "stone", "chapel", "canteen"):
                    px, py = polar_to_local(o["bearing_deg"], o["distance_m"])
                    r = math.radians(total)          # ramène au repère du cap initial (pivot cumulé)
                    seen[o["ref"]] = (px * math.cos(r) + py * math.sin(r), -px * math.sin(r) + py * math.cos(r))
            if i < steps:
                await self.turn(360 / steps)
                total += 360 / steps
                await asyncio.sleep(0.15)
        if len(seen) < 2:
            return False
        pairs = [((self.w.landmarks[r]["x"], self.w.landmarks[r]["y"]), p) for r, p in seen.items()]
        x, y, th = solve_pose(pairs)
        self.w.pose, self.w.fixed, self.w.heading_known = (x, y, norm(th + total)), True, True
        return True

    # ------------------------------------------------------------ exploration
    async def explore(self, until=None, budget=120.0, leg=14.0, gait="walk"):
        """Parcourt le village en préférant les zones jamais visitées, et complète la carte.
        S'arrête quand `until()` est vrai ou quand le budget de temps est écoulé."""
        t0 = time.time()
        while time.time() - t0 < budget and not (until and until()):
            if not self.w.usable and not await self.localize():
                await self.unstick()
                continue
            anchors = [(v["x"], v["y"]) for v in self.w.landmarks.values()]
            best = self.st.grid.frontier(self.w.pose[:2], anchors)
            if best is None:                                 # tout est balayé : direction au hasard
                x, y, _ = self.w.pose
                ang = random.uniform(0, 360)
                best = (x + leg * math.sin(math.radians(ang)), y + leg * math.cos(math.radians(ang)))
            if await self.goto(best, stop=2.5, gait=gait, timeout=25):
                # arrivé : regard circulaire pour découvrir ce qui est autour (le balayage ne couvre que l'avant)
                self.st.grid.seen.add(grid_cell(best, ZONE))
                await self.scan_around(3)
            else:
                self.st.grid.drop(best)                      # zone inaccessible : on n'y retourne pas
            await asyncio.sleep(0)                           # jamais de boucle sans rendre la main
            self.w.save()
        await self.stop()
        return until() if until else True
