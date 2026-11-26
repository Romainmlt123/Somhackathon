import math

from tests.harness import Env, run


def test_goto_bench_and_sit():
    async def go():
        async with Env(minute=720) as e:
            ok = await e.body.goto("bench2", stop=1.5)
            res = await e.body.sit("bench2")
            return ok, res, e.sim.posture
    ok, res, posture = run(go())
    assert ok and res["ok"] and posture == "sitting"


def test_enter_house_and_leave():
    async def go():
        async with Env(minute=720, start=(-10.0, -2.0)) as e:
            await e.body.scan_around()
            inside = await e.body.enter("h5")
            zones = list(e.sim.zones())
            out = await e.body.leave("h5")
            return inside, zones, out, e.sim.zones()
    inside, zones, out, zones_after = run(go())
    assert inside and "home" in zones
    assert out and "home" not in zones_after


def test_sleep_in_own_bed_then_stand():
    async def go():
        async with Env(minute=1400, start=(-10.0, -2.0)) as e:
            await e.body.scan_around()
            await e.body.enter("h5")
            r = await e.body.sleep()
            st1 = e.sim.posture
            await e.body.stand()
            return r, st1, e.sim.posture
    r, st1, st2 = run(go())
    assert r["ok"] and st1 == "sleeping" and st2 == "standing"


def test_return_home_then_relocalize():
    async def go():
        async with Env(minute=720, start=(-10.0, -2.0)) as e:
            await e.body.scan_around()
            await e.body.enter("h5")           # mémorise l'intérieur
            await e.body.leave("h5")
            await e.body.goto("campfire", stop=3)
            res = await e.body.return_home()
            import asyncio
            await asyncio.sleep(10.8)
            e.state.world.lose_pose()
            ok = await e.body.localize()
            return res, ok, "home" in e.sim.zones(), e.state.world.pose, (e.sim.x, e.sim.y, e.sim.heading)
    res, ok, home, pose, truth = run(go(), timeout=90)
    assert res["ok"] and home and ok


def test_read_and_write_board():
    async def go():
        async with Env(minute=720) as e:
            await e.body.write_board("bonjour")
            return await e.body.read_board()
    entries = run(go())
    assert entries and entries[0]["text"] == "bonjour"


def test_wolf_full_night_flow():
    """Loup : trouve la pierre, se transforme, entre dans une maison, attaque ; la chasse finie, il redevient humain."""
    async def go():
        async with Env(role="wolf", minute=720, start=(0.0, -12.0)) as e:
            e.sim.persons["p3"] = ("Émile", (-9.5, 6.6))      # dort dans la maison n°5
            # de jour : on cartographie (la pierre, les maisons) ; de nuit on ne voit qu'à 8 m
            found = await e.body.explore(until=lambda: e.state.world.of_kind("stone") and e.state.world.door_of("h5"), budget=100)
            e.sim.minute = 1400
            await e.body.scan_around()
            tr = await e.body.transform()
            form_after = e.sim.form
            inside = await e.body.enter("h5")
            await e.body.scan_around()
            ref = next((r for r, v in e.state.visible.items() if v["kind"] == "person" and v["name"] == "Émile"), None)
            res = await e.body.attack(ref) if ref else None
            return found, tr, form_after, inside, ref, res, e.sim.kills, e.sim.form
    found, tr, form_after, inside, ref, res, kills, form = run(go(), timeout=150)
    assert found and tr["ok"] and form_after == "wolf"
    assert inside and ref and res["ok"] and kills == [ref]
    assert form == "human"


def test_transform_refused_for_villager():
    async def go():
        async with Env(role="villager", minute=1400, start=(0.0, 20.0)) as e:
            await e.body.scan_around()
            return await e.body.transform()
    res = run(go())
    assert not res["ok"] and res["code"] == "action_unavailable"
