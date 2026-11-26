"""Géométrie 2D. Repère de l'agent : x à droite, y devant. Angles en degrés, sens horaire positif
(0 = devant, +90 = droite), comme dans le protocole."""
import math


def norm(a):
    """Ramène un angle dans [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


def polar_to_local(bearing, dist):
    r = math.radians(bearing)
    return (dist * math.sin(r), dist * math.cos(r))


def local_to_world(p, pose):
    x, y, th = pose
    r = math.radians(th)
    c, s = math.cos(r), math.sin(r)
    return (x + p[0] * c + p[1] * s, y - p[0] * s + p[1] * c)


def world_to_local(pt, pose):
    x, y, th = pose
    r = math.radians(th)
    c, s = math.cos(r), math.sin(r)
    dx, dy = pt[0] - x, pt[1] - y
    return (dx * c - dy * s, dx * s + dy * c)


def world_to_polar(pt, pose):
    """(bearing, distance) d'un point du monde vu depuis une pose."""
    lx, ly = world_to_local(pt, pose)
    return (math.degrees(math.atan2(lx, ly)), math.hypot(lx, ly))


def solve_pose(pairs):
    """pairs : [((wx, wy), (px, py))] points connus du monde et leur position locale observée.
    Renvoie (x, y, th) par alignement rigide (Procrustes). Exige au moins 2 paires distinctes."""
    n = len(pairs)
    mw = (sum(w[0] for w, _ in pairs) / n, sum(w[1] for w, _ in pairs) / n)
    mp = (sum(p[0] for _, p in pairs) / n, sum(p[1] for _, p in pairs) / n)
    a = b = 0.0
    for w, p in pairs:
        wx, wy = w[0] - mw[0], w[1] - mw[1]
        px, py = p[0] - mp[0], p[1] - mp[1]
        a += wx * px + wy * py
        b += wx * py - wy * px
    th = math.degrees(math.atan2(b, a))
    r = math.radians(th)
    c, s = math.cos(r), math.sin(r)
    return (mw[0] - (mp[0] * c + mp[1] * s), mw[1] - (-mp[0] * s + mp[1] * c), th)


def pose_from_one(world_pt, local_pt, th):
    """Position connaissant le cap th et un repère vu en local_pt."""
    r = math.radians(th)
    c, s = math.cos(r), math.sin(r)
    return (world_pt[0] - (local_pt[0] * c + local_pt[1] * s),
            world_pt[1] - (-local_pt[0] * s + local_pt[1] * c), th)


def heading_vec(th):
    r = math.radians(th)
    return (math.sin(r), math.cos(r))
