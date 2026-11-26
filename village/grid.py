"""Grille d'obstacles alimentée par les balayages, planificateur A* et frontières d'exploration.

Inspiré du joueur de référence des organisateurs : les rayons libres effacent les obstacles, les impacts en ajoutent,
une collision réelle est mémorisée 25 s (un corps accroche souvent un angle que le rayon central déclare libre) et
les cases jamais vues sont franchissables. Repère : celui de la carte (x à droite, y devant, cap horaire).
"""
import heapq
import math

PAS = 0.5            # côté d'une cellule d'obstacles (m)
ZONE = 6.0           # côté d'une cellule d'exploration (m)
PORTEE_OBSTACLE = 14.0
VOISINS = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]


def cell(p, pas=PAS):
    return (math.floor(p[0] / pas), math.floor(p[1] / pas))


def center(c, pas=PAS):
    return ((c[0] + 0.5) * pas, (c[1] + 0.5) * pas)


def ray(th_deg, d=1.0):
    r = math.radians(th_deg)
    return (d * math.sin(r), d * math.cos(r))


class Grid:
    def __init__(self):
        self.cells = {}        # cellule -> confiance d'obstacle (-4 libre ... 8 mur)
        self.walls = set()
        self.heurts = {}       # cellule -> fin de validité (s)
        self.seen = set()      # zones d'exploration déjà balayées
        self.dropped = set()   # zones d'exploration inaccessibles

    # ---- alimentation
    def integrate(self, pose, scan):
        """Inscrit un balayage pris depuis `pose` = (x, y, cap)."""
        if not scan:
            return
        x, y, th = pose
        rng = scan["range_m"]
        for i, (dist, kind) in enumerate(zip(scan["distances_m"], scan["kinds"])):
            dx, dy = ray(th + scan["from_deg"] + (i + 0.5) * scan["step_deg"])
            free = rng if dist is None else dist
            if kind == "body":
                free = max(0.0, free - 0.6)
            d = PAS
            while d < free - 0.35:
                c = cell((x + d * dx, y + d * dy))
                self._set(c, max(-4, self.cells.get(c, 0) - 1))
                d += PAS
            for k in range(0, int(min(free, rng)), 3):
                self.seen.add(cell((x + k * dx, y + k * dy), ZONE))
            if dist is not None and kind != "body" and dist <= PORTEE_OBSTACLE:
                c = cell((x + (dist + 0.1) * dx, y + (dist + 0.1) * dy))
                self._set(c, min(8, max(self.cells.get(c, 0), 0) + 3))
        self.seen.add(cell((x, y), ZONE))

    def _set(self, c, v):
        self.cells[c] = v
        if v >= 2 or c in self.heurts:
            self.walls.add(c)
        else:
            self.walls.discard(c)

    def mark_heurt(self, p, until):
        c = cell(p)
        self.heurts[c] = until
        self.walls.add(c)

    def forget_heurts(self, now):
        for c, end in list(self.heurts.items()):
            if end <= now:
                del self.heurts[c]
                if self.cells.get(c, 0) < 2:
                    self.walls.discard(c)

    # ---- requêtes
    def line_free(self, a, b, width=0.4):
        """Un corps peut-il suivre le segment sans frôler un obstacle connu ?"""
        L = math.dist(a, b)
        if L < 1e-6:
            return True
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        sx, sy = -uy * width, ux * width
        for k in range(1, max(1, int(L / 0.25)) + 1):
            p = (a[0] + (b[0] - a[0]) * k / max(1, int(L / 0.25)), a[1] + (b[1] - a[1]) * k / max(1, int(L / 0.25)))
            if cell(p) in self.walls or cell((p[0] + sx, p[1] + sy)) in self.walls or cell((p[0] - sx, p[1] - sy)) in self.walls:
                return False
        return True

    def plan(self, start, goal, tol=1.0, limit=6000):
        """Plus court chemin (liste de points) ; les cases inconnues sont franchissables."""
        s, g = cell(start), cell(goal)
        if s == g:
            return [goal]
        margin = int(18 / PAS)
        lo_x, hi_x = min(s[0], g[0]) - margin, max(s[0], g[0]) + margin
        lo_y, hi_y = min(s[1], g[1]) - margin, max(s[1], g[1]) + margin
        walls, known = self.walls, self.cells

        def rest(c):
            dx, dy = abs(c[0] - g[0]), abs(c[1] - g[1])
            return (max(dx, dy) + 0.414 * min(dx, dy)) * PAS

        costs, parent = {s: 0.0}, {}
        heap = [(rest(s), 0.0, s)]
        best, seen = s, 0
        while heap and seen < limit:
            _, cost, c = heapq.heappop(heap)
            if cost > costs.get(c, math.inf):
                continue
            seen += 1
            if rest(c) < rest(best):
                best = c
            if math.dist(center(c), goal) <= tol or c == g:
                best = c
                break
            for dx, dy in VOISINS:
                n = (c[0] + dx, c[1] + dy)
                if not (lo_x <= n[0] <= hi_x and lo_y <= n[1] <= hi_y) or n in walls:
                    continue
                if dx and dy and ((c[0] + dx, c[1]) in walls or (c[0], c[1] + dy) in walls):
                    continue                                   # pas de coupe d'angle
                w = 1.0 if n in known else 1.25
                x, y = n
                if any((x + i, y + j) in walls for i, j in VOISINS):
                    w += 2.5                                   # on s'écarte des murs
                new = cost + PAS * (1.414 if dx and dy else 1.0) * w
                if new < costs.get(n, math.inf):
                    costs[n], parent[n] = new, c
                    heapq.heappush(heap, (new + 1.6 * rest(n), new, n))   # heuristique gonflée : un peu plus long, bien plus vite
        path, c = [], best
        while c != s:
            path.append(center(c))
            c = parent[c]
        path.reverse()
        if math.dist(center(best), goal) <= max(tol, PAS):
            path.append(goal)
        return path or [goal]

    def waypoint(self, pos, path, reach=4.0):
        """Point du chemin le plus lointain atteignable en ligne droite (≤ reach m)."""
        if not path:
            return None
        if math.dist(pos, path[-1]) < 6 and self.line_free(pos, path[-1]):
            return path[-1]
        choice = path[0]
        for p in path:
            if math.dist(p, pos) > reach:
                break
            if self.line_free(pos, p):
                choice = p
        if math.dist(choice, pos) < 0.3 and len(path) > 1:
            choice = path[1]
        return choice

    # ---- exploration par frontières
    def frontier(self, pos, anchors, radius=48.0):
        """Zone voisine d'une zone vue mais jamais balayée, la plus proche de `pos`."""
        mid = (sum(a[0] for a in anchors) / len(anchors), sum(a[1] for a in anchors) / len(anchors)) if anchors else pos
        n = int(radius / ZONE)
        base = cell(mid, ZONE)
        free = [c for c in ((base[0] + i, base[1] + j) for i in range(-n, n + 1) for j in range(-n, n + 1))
                if c not in self.seen and c not in self.dropped
                and any((c[0] + i, c[1] + j) in self.seen for i, j in VOISINS)]
        if not free:
            self.dropped.clear()
            return None
        # proche de nous, mais on reste autour du village (centre des repères) plutôt que de dériver dans le vide
        return center(min(free, key=lambda c: math.dist(center(c, ZONE), pos) + 0.8 * math.dist(center(c, ZONE), mid)), ZONE)

    def drop(self, p):
        self.dropped.add(cell(p, ZONE))
