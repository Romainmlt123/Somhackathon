# Carte des décisions de l'agent

Première cartographie : quelles décisions l'agent doit prendre, quand, avec quelles options, et comment [moteur_probas.py](moteur_probas.py) les note. Sources : [PROTOCOLE.md](PROTOCOLE.md) et l'aide-mémoire de [Régles/LIVRET.md](Régles/LIVRET.md).

## Principe

Le moteur de décision voit deux sortes de décisions :

1. **Les invitations** (`decision_request`) : le serveur propose une liste fermée d'options avec une échéance. `evaluer(ctx, request)` note chaque option.
2. **L'agenda** : hors invitation, que faire maintenant (marcher, écouter, rentrer…). `evaluer_agenda(ctx)` note les activités possibles selon l'heure et le rôle.

Chaque option reçoit une **utilité** entre 0 et 1, calculée à partir du graphe (`p(loup)` de chaque joueur, rôles révélés, Capitaine) et des règles (points, potions, horaires). Un softmax (température 0,15) les transforme en **probabilités**. La **confiance** est l'écart entre les deux meilleures options. Sous 0,15, `consulter_modele` passe à vrai : seuls ces cas ambigus vont au modèle, ce qui sert le prix de Sobriété.

`Resultat.pour_journal()` donne les champs à passer à `journal.why(...)`, pour pouvoir relire chaque choix après la partie.

## Branchement dans l'agent

Le graphe est la seule source de connaissance du moteur de décision :

```
journal ──► graphe.observe ──► Contexte.depuis_graphe ──► evaluer ──► village/rules.py (do_vote, do_choice) ──► act
```

`Contexte.depuis_graphe` lit dans [graphe.py](graphe.py) : `p(loup)` de chaque joueur (`proba_loup`), les rôles certains (`A_LE_ROLE`), les vivants et les morts, le Capitaine (`capitaine()`), les accusations entendues (`nb_accusations`, arêtes `ACCUSE`), les rôles revendiqués (`pretentions`, arêtes `PRETEND_ETRE`), les partenaires loups (`loups_connus`), les potions déjà bues (`potions_utilisees`) et les inspections faites (`nb_inspections`).

| Invitation | Qui décide | Repli |
|---|---|---|
| Vote du conseil, élection du Capitaine | Le moteur de probabilités (`Rules.do_vote`). Le modèle ne départage que si la confiance est sous 0,15 (`consulter_modele`), et seulement vers une option d'utilité supérieure à 0,05. | Le modèle seul, si le moteur ne rend rien. |
| Inspection, potion, succession | Le moteur de probabilités (`Rules.do_choice`). | Le modèle, si la situation est ambiguë. |
| Épreuve | `epreuves.py`, puis le modèle | — |

L'agent qui joue est `run_agent.py` → [village/brain.py](village/brain.py) → [village/rules.py](village/rules.py), qui partage le même `Graphe` que le journal. Le corps historique [agent.py](agent.py) n'utilise plus le moteur de probabilités.

Les règles C, V et L de l'étude sont intégrées aux utilités : chaque raison commence par son code (`V2`, `V7`, `L9`, `L10`…), que `Resultat.regle` extrait pour le journal.

- **C2** : soi-même et les morts valent 0.
- **V2** : loup certain = 1, innocent certain = 0, sinon `p(loup)` + un bonus de popularité (0,02 par accusation, plafonné à 0,1).
- **V7** : un rôle à pouvoir déclaré dont `p(loup)` < 0,75 tombe à 0,3 × p.
- **L9** : un allié vaut 0, sauf s'il est déjà condamné (au moins 2 accusations et le plus accusé) : 0,95.
- **L10** : le loup vise un rôle à pouvoir déclaré (+0,2) ou l'innocent le plus accusé.
- **V8** : inspection = 0,5 × p + 0,4 × entropie, +0,1 pour le Capitaine.

## Les invitations

| `kind` | Qui | Quand | Options | Règle de notation |
|---|---|---|---|---|
| `captain_election` | Tous | Jour 1, 9 h-11 h, au feu | Un candidat (soi compris) | Village : confiance = 1 − p(loup), moins la popularité des accusations. Loup : un allié 0,9, sinon le moins accusé. Jamais soi (C2). |
| `council_vote` | Tous les vivants | Vote de 19 h à 21 h, au feu, bulletin définitif | Un candidat, même absent | Village : utilité = p(loup), puisque chaque vote contre un loup rapporte 1 point. Loup : jamais un allié ; vote pour l'innocent le plus soupçonné, pour rester crédible. |
| `seer_inspect` | Voyante | 22 h-8 h, depuis sa maison, 2 par manche, 1 par nuit | Un habitant | Moitié soupçon, moitié entropie de p(loup). +0,1 pour le Capitaine. 0 si le rôle est déjà connu. |
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
- **Rôle du joueur** : `Contexte.depuis_graphe` le lit dans le graphe (`A_LE_ROLE` de soi) ; l'agent passe aussi `mon_role=self.role()`.
