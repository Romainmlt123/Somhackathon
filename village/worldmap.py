"""Carte des repères fixes et localisation de l'agent.

Le serveur ne donne aucune coordonnée, mais les repères fixes (maisons, portes, lits, bancs, feu,
panneau, pierre) ont des références stables et des observations exactes (angle + distance). On
construit donc une carte dans un repère propre à l'équipe, et on retrouve la pose (x, y, cap) de
l'agent à chaque message `vision`. La carte est sauvegardée en JSON : elle reste valable d'une
connexion à l'autre et peut être partagée par toute l'équipe.
"""
import json
import math
import time
from pathlib import Path

from .geometry import (heading_vec, local_to_world, norm, polar_to_local, pose_from_one,
                       solve_pose, world_to_polar)

STATIC_KINDS = {"house", "door", "bed", "bench", "campfire", "board", "stone", "chapel", "canteen"}
SPEED = {"sneak": 0.83, "walk": 1.81, "run": 3.6}  # m/s, à affiner par mesure (run provisoire)


class WorldMap:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.landmarks = {}     # ref -> {"x","y","kind","name"?,"of"?}
        self.pose = (0.0, 0.0, 0.0)
        self.fixed = False      # la pose vient-elle d'un repère connu (vs estimée à l'aveugle) ?
        self.tentative = False  # pose rechargée du disque : à confirmer par un repère
        self.fix_t = 0.0
        self.motion = None      # (gait, direction absolue en degrés) du mouvement en cours
        self._t = time.time()
        self.dirty = False
        if self.path and self.path.exists():
            data = json.loads(self.path.read_text())
            self.landmarks = data["landmarks"]
            if data.get("pose"):
                self.pose = tuple(data["pose"])
                self.tentative = True

    # ---- persistance
    def save(self, force=False):
        if self.path and (self.dirty or force):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {"landmarks": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv)
                                      for kk, vv in v.items()} for k, v in sorted(self.landmarks.items())}}
            if self.fixed:
                data["pose"] = [round(v, 3) for v in self.pose]
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            self.dirty = False

    # ---- estimation de pose
    def advance(self, now=None):
        """Navigation à l'estime entre deux repères : avance selon l'allure en cours."""
        now = now or time.time()
        dt = max(0.0, min(now - self._t, 30.0))
        self._t = now
        if self.motion and self.motion[0] in SPEED:
            x, y, th = self.pose
            hx, hy = heading_vec(self.motion[1])
            v = SPEED[self.motion[0]] * dt
            self.pose = (x + hx * v, y + hy * v, th)

    def note_turn(self, angle):
        self.advance()
        x, y, th = self.pose
        self.pose = (x, y, norm(th + angle))

    def set_motion(self, gait, bearing=0.0):
        self.advance()
        # le serveur fixe la direction dans le monde à l'instant de l'ordre : un `turn` ultérieur ne la change pas
        self.motion = None if gait in (None, "stop") else (gait, norm(self.pose[2] + bearing))

    def lose_pose(self):
        """Après une téléportation (retour à la maison) : la pose n'est plus connue."""
        self.fixed = self.tentative = False

    def observe(self, observations, now=None):
        """Met à jour la pose et la carte avec les observations d'un même instant."""
        now = now or time.time()
        self.advance(now)
        statics = [o for o in observations if o["kind"] in STATIC_KINDS]
        if not statics:
            return
        known = [o for o in statics if o["ref"] in self.landmarks]
        if not self.landmarks:  # première fois : le repère naît ici
            self.pose = (0.0, 0.0, 0.0)
            self.fixed = True
        elif len(known) >= 2 and self._distinct(known):
            pairs = [((self.landmarks[o["ref"]]["x"], self.landmarks[o["ref"]]["y"]),
                      polar_to_local(o["bearing_deg"], o["distance_m"])) for o in known]
            self.pose = solve_pose(pairs)
            self.fixed = True
        elif len(known) == 1 and (self.fixed or self.tentative):
            o = known[0]
            lm = self.landmarks[o["ref"]]
            cand = pose_from_one((lm["x"], lm["y"]), polar_to_local(o["bearing_deg"], o["distance_m"]), self.pose[2])
            if self.fixed or math.dist(cand[:2], self.pose[:2]) < 2.5:
                self.pose, self.fixed = cand, True   # cap connu (suivi des pivots) + un repère
        else:
            return  # pas assez de repères connus : on n'ajoute rien à l'aveugle
        if not self.fixed:
            return
        self.fix_t = now
        for o in statics:
            if o["ref"] not in self.landmarks:
                x, y = local_to_world(polar_to_local(o["bearing_deg"], o["distance_m"]), self.pose)
                lm = {"x": x, "y": y, "kind": o["kind"]}
                if o.get("name"):
                    lm["name"] = o["name"]
                if o.get("of"):
                    lm["of"] = o["of"]
                self.landmarks[o["ref"]] = lm
                self.dirty = True

    @staticmethod
    def _distinct(obs):
        a = polar_to_local(obs[0]["bearing_deg"], obs[0]["distance_m"])
        return any(math.dist(a, polar_to_local(o["bearing_deg"], o["distance_m"])) > 0.05 for o in obs[1:])

    # ---- requêtes
    def xy(self, ref):
        lm = self.landmarks.get(ref)
        return (lm["x"], lm["y"]) if lm else None

    def polar_to(self, target):
        """(bearing, distance) depuis la pose courante vers une réf. connue ou un point (x, y)."""
        pt = self.xy(target) if isinstance(target, str) else target
        return world_to_polar(pt, self.pose) if pt else None

    def of_kind(self, kind):
        return [r for r, v in self.landmarks.items() if v["kind"] == kind]

    def nearest(self, kind):
        c = [(self.polar_to(r)[1], r) for r in self.of_kind(kind)]
        return min(c)[1] if c else None

    def door_of(self, house):
        return next((r for r, v in self.landmarks.items() if v["kind"] == "door" and v.get("of") == house), None)

    def door_frame(self, house):
        """Géométrie d'entrée d'une maison : (point extérieur, porte, point intérieur) sur la normale de la porte."""
        d, h = self.door_of(house), self.xy(house)
        dp = self.xy(d) if d else None
        if not dp or not h:
            return None
        vx, vy = dp[0] - h[0], dp[1] - h[1]
        n = math.hypot(vx, vy) or 1.0
        ux, uy = vx / n, vy / n
        return ((dp[0] + ux * 2.0, dp[1] + uy * 2.0), dp, (dp[0] - ux * 1.5, dp[1] - uy * 1.5))
