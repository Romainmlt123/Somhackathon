"""Gameplay loup dans le simulateur : repérer la pierre de jour, se transformer, fouiller les maisons, attaquer."""
import asyncio

from tests.harness import Env, make_brain, run, until


def test_wolf_scouts_the_stone_by_day():
    async def go():
        async with Env(preload=True, role="wolf", minute=720, start=(0.0, -12.0)) as e:
            e.state.world.landmarks.pop("stone")                      # la pierre n'est pas encore sur la carte
            br, llm = make_brain(e)
            t = asyncio.create_task(br.run())
            ok = await until(lambda: "stone" in e.state.world.landmarks, 100)
            t.cancel()
            return ok
    assert run(go(), 130)


def test_wolf_pack_member_is_refused_then_another_victim_is_killed():
    async def go():
        async with Env(preload=True, role="wolf", minute=1340, start=(0.0, -12.0)) as e:
            e.sim.persons["p3"] = ("Émile", (13.0, 8.9))               # loup de la meute, dans la maison n°4, près de l'entrée
            e.sim.persons["p4"] = ("Léa", (14.8, 7.2))                 # villageoise, plus au fond
            e.sim.person_posture.update(p3="sleeping", p4="sleeping")
            e.sim.pack.add("p3")
            br, llm = make_brain(e)
            t = asyncio.create_task(br.run())
            ok = await until(lambda: e.sim.kills, 150)
            t.cancel()
            return ok, e.sim.kills, br.rules.meute
    ok, kills, meute = run(go(), 180)
    assert ok and kills == ["p4"]                                   # jamais le loup de la meute


def test_wolf_searches_several_houses_before_finding_the_victim():
    async def go():
        async with Env(preload=True, role="wolf", minute=1340, start=(0.0, -12.0)) as e:
            e.sim.persons["p3"] = ("Émile", (13.8, 8.6))               # seulement dans la maison n°4, la plus éloignée
            e.sim.person_posture["p3"] = "sleeping"
            for k in ("p1", "p2"):
                e.sim.persons.pop(k)
            br, llm = make_brain(e)
            t = asyncio.create_task(br.run())
            ok = await until(lambda: e.sim.kills, 170)
            t.cancel()
            return ok, e.sim.kills, e.sim.form, sorted(br.rules.searched)
    ok, kills, form, searched = run(go(), 200)
    assert ok and kills == ["p3"] and form == "human"
