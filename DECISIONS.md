# Carte des décisions de l'agent

Première cartographie : quelles décisions l'agent doit prendre, quand, avec quelles options, et comment [moteur_probas.py](moteur_probas.py) les note. Sources : [PROTOCOLE.md](PROTOCOLE.md) et l'aide-mémoire de [Régles/LIVRET.md](Régles/LIVRET.md).

## Principe

Le moteur de décision voit deux sortes de décisions :

1. **Les invitations** (`decision_request`) : le serveur propose une liste fermée d'options avec une échéance. `evaluer(ctx, request)` note chaque option.
2. **L'agenda** : hors invitation, que faire maintenant (marcher, écouter, rentrer…). `evaluer_agenda(ctx)` note les activités possibles selon l'heure et le rôle.

Chaque option reçoit une **utilité** entre 0 et 1, calculée à partir du graphe (`p(loup)` de chaque joueur, rôles révélés, Capitaine) et des règles (points, potions, horaires). Un softmax (température 0,15) les transforme en **probabilités**. La **confiance** est l'écart entre les deux meilleures options. Sous 0,15, `consulter_modele` passe à vrai : seuls ces cas ambigus vont au modèle, ce qui sert le prix de Sobriété.

`Resultat.pour_journal()` donne les champs à passer à `journal.why(...)`, pour pouvoir relire chaque choix après la partie.

## Les invitations

| `kind` | Qui | Quand | Options | Règle de notation |
|---|---|---|---|---|
| `captain_election` | Tous | Jour 1, 9 h-11 h, au feu | Un candidat (soi compris) | Village : confiance = 1 − p(loup) ; se choisir vaut 0,6. Loup : soi 0,9, un allié 0,8. |
| `council_vote` | Tous les vivants | Vote de 19 h à 21 h, au feu, bulletin définitif | Un candidat, même absent | Village : utilité = p(loup), puisque chaque vote contre un loup rapporte 1 point. Loup : jamais un allié ; vote pour l'innocent le plus soupçonné, pour rester crédible. |
| `seer_inspect` | Voyante | 22 h-8 h, depuis sa maison, 2 par manche, 1 par nuit | Un habitant | Entropie de p(loup) : on inspecte là où l'on doute le plus. +0,15 pour le Capitaine. 0 si le rôle est déjà connu. |
| `witch_potion` | Sorcière | Nuit, depuis sa maison, avant 8 h, 1 potion par nuit | `heal` sur une victime, `poison` sur un habitant, abstention | Vie : 0,9 − 0,8 × p(loup) de la victime, avec un bonus si c'est soi, le Capitaine ou la Voyante. Mort : seulement si p(loup) ≥ 0,8. Garder ses potions vaut 0,35. |
| `witch_self_rescue` | Sorcière tuée chez elle | Nuit | Se sauver | Toujours oui. |
| `captain_succession` | Capitaine mourant | 10 s | Un vivant | Village : 1 − p(loup). Loup : un allié. |
| `challenge_answer` | Présents à l'épreuve IA | 15 h, sur le lieu annoncé | `choice`, `multi_choice` ou `text` | Pas de notation locale : c'est une question de contenu, elle va au modèle. |

## Les actions libres

| Décision | Qui | Quand | Notation |
|---|---|---|---|
| **Attaquer** (`transform` puis `attack`) | Loup | 22 h-6 h, cible à 2 m | `cibles_attaque()` : base 0,4, +0,35 pour une Voyante ou une Sorcière révélée, +0,2 pour le Capitaine, +0,25 pour quelqu'un qui m'a accusé, −0,2 × p(loup), car un suspect sera de toute façon éliminé au conseil. |
| **Accuser à voix haute** (`speak`) | Village | Journée | Si le joueur le plus suspect a p(loup) ≥ 0,7. |
| **Dormir** | Tous sauf un loup en chasse | 22 h-8 h, dans un lit | Moins de 7 h de sommeil donne de la fatigue (l'ouïe baisse). |
| **Rentrer** (`return_home`) | Tous | À partir de 21 h 30 | Le transport prend 10 s, avec une demande par minute au plus. |
| **Aller à l'épreuve** | Tous | Annonce à 14 h, ouverture à 15 h | Il faut être présent à la clôture : 1 point pour le village si l'épreuve réussit, 2 points pour un loup si elle échoue. |
| **Aller au conseil** | Tous | 17 h-21 h | Prioritaire, car c'est là que se marquent les points. |
| **Explorer ou écouter** | Tous | Le reste de la journée | Fond d'activité : il alimente le graphe. |
| **Écrire au tableau** (`write_board`), **gestes** | Tous | Une publication par 60 s | Pas encore noté. À brancher sur la stratégie de parole. |

## Ce qui reste à décider

- **Paroles du loup** : faut-il accuser un innocent ? Le moteur ne le note pas encore.
- **Calibrage** : les poids et les seuils (0,7 pour accuser, 0,8 pour empoisonner, température) sont posés à la main. Il faudra les ajuster sur les journaux de vraies manches avec `python graphe.py traces/X.jsonl`.
- **Popularité d'un candidat** : pour un loup, suivre le vote majoritaire serait mieux que suivre `p(loup)`. Il faudrait compter les accusations entendues (arêtes `ACCUSE`).
- **Rôle du joueur** : `Contexte.depuis_graphe` le lit dans le graphe. S'il n'y est pas, il faut passer `mon_role=st.role`.
