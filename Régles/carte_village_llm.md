# Carte du village, version lisible par un LLM

Source : `carte village.png` (briefing « Carte du village »).

**Attention aux numéros.** Les numéros 1 à 5 désignent à la fois des **lieux** (cercles dorés) et des **maisons** (badges blancs sur les bâtiments). Dans ce document, les lieux s'écrivent toujours « Lieu n » et les maisons « Maison nº n ». Ne les confondez jamais : Maison nº 3 et Lieu 3 (la Chapelle) sont deux endroits différents.

Le plan est donné en vue de dessus, **le haut de l'image vers le nord**. Les positions sont approximatives et servent à raisonner sur la topologie (qui est relié à quoi), pas à calculer des distances exactes.

## 1. Lieux (cercles dorés)

| Repère | Nom | Position sur le plan | Rôle |
|---|---|---|---|
| **Lieu 1** | Feu du conseil | Centre du village, sur une place circulaire | Élection et votes du village |
| **Lieu 2** | Cantine | Nord-est, bâtiment à toit turquoise | Rendez-vous et épreuves |
| **Lieu 3** | Chapelle | Nord-ouest, bâtiment à toit bleu-gris | Rendez-vous et épreuves |
| **Lieu 4** | Panneau | Ouest de la place, juste à côté du feu | Journal anonyme des habitants |
| **Lieu 5** | Clairière de la meute | Nord, au-dessus de la place, enclos de buissons | Pierre de transformation |

## 2. Maisons (badges blancs)

Les maisons sont alignées de part et d'autre de deux routes verticales, plus une rangée en bas.

| Repère | Côté | Position | Chemin d'accès |
|---|---|---|---|
| **Maison nº 1** | Ouest | Rangée haute de l'ouest | Route ouest, branche courte |
| **Maison nº 2** | Est | Rangée haute de l'est (toit rouge) | Route est, branche courte |
| **Maison nº 3** | Ouest | Rangée du milieu ouest (toit bleu) | Route ouest |
| **Maison nº 4** | Est | Rangée du milieu est (toit vert) | Route est |
| **Maison nº 5** | Ouest | Rangée basse de l'ouest (toit rouge) | Route ouest |
| **Maison nº 6** | Est | Rangée basse de l'est (toit bleu) | Route est |
| **Maison nº 7** | Ouest | Tout en bas à gauche de la rangée ouest (toit vert) | Route ouest |
| **Maison nº 8** | Est | Tout en bas à droite de la rangée est (toit rouge) | Route est |
| **Maison nº 9** | Sud | Rangée du bas, extrême gauche | Route du bas |
| **Maison nº 10** | Sud | Rangée du bas, deuxième | Route du bas |
| **Maison nº 11** | Sud | Rangée du bas, centre (toit rouge) | Route du bas, près de la route centrale sud |
| **Maison nº 12** | Sud | Rangée du bas, quatrième | Route du bas |
| **Maison nº 13** | Sud | Rangée du bas, extrême droite | Route du bas |

Un bâtiment rouge sans badge se trouve entre la Maison nº 2 et la Maison nº 4, à l'est. Il n'a pas de numéro sur le plan : ne le considérez pas comme une maison.

## 3. Routes

Il y a trois axes verticaux et un axe horizontal en bas.

- **Route ouest** : longe le côté ouest du village, du nord au sud. Elle dessert les Maisons nº 1, 3, 5 et 7 par de courtes branches.
- **Route est** : longe le côté est. Elle dessert les Maisons nº 2, 4, 6 et 8.
- **Route centrale** : part du Lieu 5 (Clairière) vers le sud, traverse la place du Lieu 1 et continue jusqu'à la route du bas.
- **Route du bas** : horizontale, au sud, elle relie les Maisons nº 9 à 13 et la route centrale.
- **Carrefour nord** : au-dessus de la place, se rejoignent la route centrale et deux chemins diagonaux, l'un vers le Lieu 3 (Chapelle), l'autre vers le Lieu 2 (Cantine).
- **Place du Feu** : quatre sorties, à l'ouest vers la route ouest, à l'est vers la route est, au nord vers la route centrale, au sud vers la route centrale. Le Lieu 4 (Panneau) se trouve à l'ouest de la place, sur la sortie ouest.

## 4. Graphe de connexions (résumé)

```
Lieu 5 (Clairière) ──route centrale nord── Place du Feu (Lieu 1)
Place du Feu (Lieu 1) ── Lieu 4 (Panneau)           [sortie ouest]
Place du Feu (Lieu 1) ── route ouest               [sortie ouest]
Place du Feu (Lieu 1) ── route est                 [sortie est]
Place du Feu (Lieu 1) ── route centrale sud ── route du bas
Carrefour nord ── Lieu 3 (Chapelle)
Carrefour nord ── Lieu 2 (Cantine)
Carrefour nord ── route centrale nord ── Lieu 5
route ouest ── Maisons nº 1, 3, 5, 7
route est   ── Maisons nº 2, 4, 6, 8
route du bas ── Maisons nº 9, 10, 11, 12, 13
```

## 5. Schéma approximatif

```
        [Lieu 3 Chapelle]                   [Lieu 5 Clairière]   [Lieu 2 Cantine]
                       \                          |                     /
                        \_________ Carrefour nord_|____________________/
                                                  |
  Maison 1 ─┐                                   Lieu 4        ┌─ Maison 2
  Maison 3 ─┤  route ouest     Place du Feu     (Panneau)     ├─ Maison 4   route est
  Maison 5 ─┤                   (Lieu 1)                      ├─ Maison 6
  Maison 7 ─┘                                                 └─ Maison 8
                                     |
           Maison 9  Maison 10  Maison 11  Maison 12  Maison 13   (route du bas)
```

Le schéma ASCII est indicatif. Il ne remplace pas le plan.

## 6. Ce que cela implique pour l'agent

- Un habitant ne voit pas la carte. Il perçoit les lieux et les maisons dans son champ de vision, avec des angles et des distances relatifs (`vision`, `bearing_deg`, `distance_m`), comme le prévoit `PROTOCOLE.md`.
- Le nom de sa maison est dans `self.home` (par exemple « Maison nº 5 »), et les messages ne donnent jamais sa position.
- Cette carte sert à raisonner sur la topologie : quel chemin prendre vers le Feu depuis une maison, ou quelle porte correspond à quelle maison. Ne transmettez pas de coordonnées absolues dans des messages d'état, puisque le protocole n'en prévoit pas.
