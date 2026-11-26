"""Compétence « parler » : une réplique de random_sentences.md s'ajoute au hasard à ce que dit l'agent."""
import asyncio
import random

import moteur
from tests.harness import Env, make_brain, run, until
from village.parler import FICHIER, charger, habiller


def test_le_fichier_est_lu_replique_par_replique():
    repliques = charger()
    assert len(repliques) >= 60
    assert all(r and "\n" not in r and r == r.strip() for r in repliques)
    assert "C’est pas faux !" in repliques


def test_une_replique_sur_plusieurs_lignes_ne_fait_qu_une_replique(tmp_path):
    f = tmp_path / "r.md"
    f.write_text("\n\n  Première.\n\n\n\n  Deuxième ligne un\n  deuxième ligne deux\n\n\n  Troisième.\n", encoding="utf-8")
    assert charger(f) == ["Première.", "Deuxième ligne un deuxième ligne deux", "Troisième."]


def test_fichier_absent_ne_plante_pas(tmp_path):
    assert charger(tmp_path / "absent.md") == []
    assert habiller("Bonjour", chemin=tmp_path / "absent.md") == ("Bonjour", None)


def test_le_texte_d_origine_reste_et_une_replique_s_ajoute():
    repliques = set(charger())
    for graine in range(50):
        texte, ajout = habiller("Léa, où étais-tu ce soir ?", rng=random.Random(graine))
        assert ajout in repliques
        assert "Léa, où étais-tu ce soir ?" in texte and ajout in texte
        assert texte in (f"Léa, où étais-tu ce soir ? {ajout}", f"{ajout} Léa, où étais-tu ce soir ?")


def test_jamais_plus_de_240_caracteres():
    for n in (1, 40, 120, 200, 235, 239):
        base = "a" * n
        for graine in range(30):
            texte, ajout = habiller(base, rng=random.Random(graine))
            assert len(texte) <= moteur.PAROLE_MAX
            assert base in texte and (ajout is None) == (texte == base)


def test_sans_place_le_texte_est_inchange():
    base = "a" * 235                                           # aucune réplique ne tient dans 4 caractères
    assert habiller(base, rng=random.Random(0)) == (base, None)


def test_le_choix_est_aleatoire_mais_reproductible_avec_une_graine():
    a = [habiller("Bonjour", rng=random.Random(7)) for _ in range(3)]
    assert a[0] == a[1] == a[2]
    assert len({habiller("Bonjour", rng=random.Random(g))[1] for g in range(40)}) > 10


def test_la_probabilite_regle_la_frequence():
    rng = random.Random(1)
    ajouts = [habiller("Bonjour", rng=rng, proba=0.3)[1] for _ in range(400)]
    part = sum(a is not None for a in ajouts) / len(ajouts)
    assert 0.2 < part < 0.4
    assert habiller("Bonjour", proba=0.0)[1] is None


def test_le_filtre_ecarte_des_repliques():
    interdite = "C’est pas faux !"
    for graine in range(80):
        _, ajout = habiller("Bonjour", accepte=lambda p: p != interdite, rng=random.Random(graine))
        assert ajout != interdite


def test_une_replique_ne_fait_pas_taire_un_loup():
    """Avec le filtre de `moteur.nettoyer`, la phrase finale n'est jamais refusée pour un loup."""
    for graine in range(60):
        texte, _ = habiller("Je dors chez moi cette nuit.", rng=random.Random(graine),
                            accepte=lambda p: moteur.nettoyer(p, (), "wolf", ()) is not None)
        assert moteur.nettoyer(texte, (), "wolf", ()) is not None


def test_texte_vide_reste_vide():
    assert habiller("") == ("", None) and habiller(None) == ("", None)


def test_le_fichier_est_bien_celui_du_depot():
    assert FICHIER.name == "random_sentences.md" and FICHIER.exists()


def test_l_agent_ajoute_une_replique_quand_il_parle():
    async def go():
        async with Env(preload=True, role="villager", minute=900, start=(0.0, -12.0)) as e:
            br, llm = make_brain(e, lambda u: {"pensee": "t", "action": "attendre", "duree": 1, "dire": "Bonjour tout le monde."})
            t = asyncio.create_task(br.run())
            await until(lambda: e.sim.spoken, 30)
            t.cancel()
            return list(e.sim.spoken)
    spoken = run(go(), 60)
    assert spoken
    texte = spoken[0][2]
    assert "Bonjour tout le monde." in texte and len(texte) <= moteur.PAROLE_MAX
    assert texte != "Bonjour tout le monde." and any(r in texte for r in charger())
