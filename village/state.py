"""État du jeu tel que l'agent le perçoit. Mis à jour de façon synchrone et rapide, message par message."""
import asyncio
import time

from .grid import Grid
from .worldmap import WorldMap


# Heure du village (en minutes) de chaque étape annoncée par le serveur. Le serveur n'envoie PAS d'horloge continue :
# on l'extrapole (un cycle jour/nuit = cycle_ms réels, soit 2,4 minutes de jeu par seconde par défaut) et on la
# recale à chaque étape connue. Relevé sur une vraie manche : 81,7 s réelles entre 10 h 43 et l'annonce de 14 h.
STEP_MINUTE = {"village_wakes": 480, "daily_program": 480, "morning_correction": 630, "challenge_announcement": 840,
               "challenge": 900, "council_call": 1020, "council_vote": 1140, "nightfall": 1320, "wolf_dawn": 360}


class GameState:
    def __init__(self, world=None):
        self.world = world or WorldMap()
        self.grid = Grid()
        self.status = "waiting_for_join"
        self.me = {}
        self.clock = {}
        self.round = None
        self.visible = {}       # ref -> observation courante (avec "t" : heure de réception)
        self.scan = None
        self.requests = {}
        self.sounds = []        # dernières paroles entendues
        self._clock_ref = None  # (minute, heure réelle, cycle_ms) du dernier recalage
        self.offset_ms = None   # heure du serveur - heure locale (le plus petit retard observé approche l'écart)
        self.version = 0        # incrémenté à chaque changement perçu
        self._ev = asyncio.Event()
        self.connected = False

    # ---- raccourcis
    @property
    def posture(self): return self.me.get("posture")
    @property
    def gait(self): return self.me.get("gait")
    @property
    def zones(self): return self.me.get("zones", [])
    @property
    def form(self): return self.me.get("form")
    @property
    def role(self): return self.me.get("role")
    @property
    def alive(self): return self.status == "alive"
    def now_ms(self):
        """Heure du serveur estimée, en ms Unix : à utiliser avec les `deadline_ms`."""
        return time.time() * 1000 + (self.offset_ms or 0.0)

    def set_clock(self, minute, cycle_ms=None):
        cycle = cycle_ms or (self._clock_ref[2] if self._clock_ref else 600000)
        self._clock_ref = (float(minute), time.time(), cycle)

    @property
    def minute(self):
        """Minute du jour (0-1439), extrapolée depuis le dernier recalage."""
        if self._clock_ref is None:
            return self.clock.get("minute")
        m0, t0, cycle = self._clock_ref
        return (m0 + (time.time() - t0) * 1000.0 / cycle * 1440.0) % 1440.0

    def hour(self):
        m = self.minute
        return None if m is None else m / 60.0

    def is_night(self):
        h = self.hour()
        return h is not None and (h >= 22 or h < 8)

    def of_kind(self, kind):
        return [v for v in self.visible.values() if v["kind"] == kind]

    def nearest(self, kind):
        c = self.of_kind(kind)
        return min(c, key=lambda v: v["distance_m"]) if c else None

    def _grid_update(self):
        """Inscrit le dernier balayage dans la grille d'obstacles, si la pose et le cap sont fiables."""
        w = self.world
        if self.status == "alive" and self.scan and w.usable and w.heading_known and not w.pending_turns:
            w.advance()
            self.grid.integrate(w.pose, self.scan)

    # ---- mise à jour
    def _changed(self):
        self.version += 1
        self._ev.set()

    async def wait_change(self, timeout=1.0):
        """Attend le prochain changement perçu (ou le délai)."""
        self._ev.clear()
        try:
            await asyncio.wait_for(self._ev.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def apply(self, frame):
        """Applique un message du serveur. Renvoie True si c'est un événement à transmettre au cerveau."""
        kind, d, now = frame["type"], frame["data"], time.time()
        if isinstance(frame.get("time_ms"), (int, float)):
            gap = frame["time_ms"] - now * 1000
            self.offset_ms = gap if self.offset_ms is None else max(self.offset_ms, gap)
        if kind == "snapshot":
            self.status = d.get("status", "alive")
            self.me = d.get("self", {})
            self.clock = d.get("clock", self.clock)
            if self.clock.get("minute") is not None:
                self.set_clock(self.clock["minute"], self.clock.get("cycle_ms"))
            self.round = d.get("round")
            self.scan = d.get("scan")
            self.requests = {r["request_id"]: r for r in d.get("requests", [])}
            self.visible = {}
            # reconnexion, mort/résurrection : on ne sait plus si l'habitant a bougé -> la pose devra être confirmée
            self.world.motion = None
            if self.world.fixed:
                self.world.fixed, self.world.tentative = False, True
            obs = d.get("visible", [])
            for o in obs:
                self.visible[o["ref"]] = {**o, "t": now}
            if self.status == "alive":
                self.world.observe(obs, now)
            self._changed()
            return True
        if kind == "vision":
            obs = d["entered"] + d["updated"]
            for o in obs:
                self.visible[o["ref"]] = {**o, "t": now}
            for r in d["left"]:
                self.visible.pop(r, None)
            self.world.observe(obs, now)
            self._changed()
            return False
        if kind == "self":
            old_gait, old_powers = self.gait, self.me.get("powers", {})
            self.me = d
            if "home_return_at_ms" in old_powers and "home_return_at_ms" not in d.get("powers", {}):
                if "home" in d.get("zones", []):
                    self.world.teleport_home(d.get("home"))   # transporté chez lui : pose exacte (centre de la maison, face au lit)
            if d.get("gait") != old_gait and d.get("gait") == "stop":
                self.world.set_motion("stop")
            self._changed()
            return False
        if kind == "scan":
            self.scan = d
            self._grid_update()
            self._changed()
            return False
        if kind == "decision_request":
            self.requests[d["request_id"]] = d
        elif kind == "decision_closed":
            self.requests.pop(d["request_id"], None)
        elif kind == "sound" and d.get("kind") == "speech":
            self.sounds.append({**d, "t": now})
            del self.sounds[:-50]
        elif kind == "game_event" and d.get("kind") == "clock_changed":
            self.clock = d.get("clock", d if "minute" in d else self.clock)
            if self.clock.get("minute") is not None:
                self.set_clock(self.clock["minute"], self.clock.get("cycle_ms"))
        elif kind == "game_event" and d.get("kind") == "scheduled_step" and d.get("step") in STEP_MINUTE:
            self.set_clock(STEP_MINUTE[d["step"]])
        self._changed()
        return kind != "command_result"
