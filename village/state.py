"""État du jeu tel que l'agent le perçoit. Mis à jour de façon synchrone et rapide, message par message."""
import asyncio
import time

from .worldmap import WorldMap


class GameState:
    def __init__(self, world=None):
        self.world = world or WorldMap()
        self.status = "waiting_for_join"
        self.me = {}
        self.clock = {}
        self.round = None
        self.visible = {}       # ref -> observation courante (avec "t" : heure de réception)
        self.scan = None
        self.requests = {}
        self.sounds = []        # dernières paroles entendues
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
    @property
    def minute(self): return self.clock.get("minute")

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
        if kind == "snapshot":
            self.status = d.get("status", "alive")
            self.me = d.get("self", {})
            self.clock = d.get("clock", self.clock)
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
                    self.world.lose_pose()        # transporté chez lui : la pose sera retrouvée sur les repères intérieurs
            if d.get("gait") != old_gait and d.get("gait") == "stop":
                self.world.set_motion("stop")
            self._changed()
            return False
        if kind == "scan":
            self.scan = d
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
            self.clock = d.get("clock", self.clock)
        self._changed()
        return kind != "command_result"
