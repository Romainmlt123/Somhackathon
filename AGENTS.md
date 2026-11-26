# Guide du dépôt pour les agents de code

Ce dépôt contient l'agent Python de l'équipe pour le jeu du village (Loup-Garou). Un seul process de l'équipe peut être connecté au serveur : une seconde connexion reçoit HTTP 409. Ne lancez donc pas `agent.py` sans l'accord de l'équipe.

## Où trouver quoi

| Besoin | Fichier |
|---|---|
| Contrat WebSocket : messages, champs, codes de refus | [PROTOCOLE.md](PROTOCOLE.md) |
| Démarrage, nouveautés du serveur, budget IA | [README.md](README.md) |
| Règles du jeu (71 cartes, aide-mémoire chiffré en fin de fichier) | [Régles/LIVRET.md](Régles/LIVRET.md) |
| Plan du village décrit pour un LLM | [Régles/carte_village_llm.md](Régles/carte_village_llm.md) |
| Connexion, file des messages reçus, envoi des commandes | [client.py](client.py) |
| Règles de conduite de l'habitant, et leur justification | [Régles/ETUDE_LOUP_GAROU.md](Régles/ETUDE_LOUP_GAROU.md) |
| Moteur de règles : où aller, qui viser, quoi dire (sans réseau) | [moteur.py](moteur.py) |
| Épreuves IA calculées sur le poste | [epreuves.py](epreuves.py) |
| Corps de l'agent, qui exécute le moteur : `Explorer.decide` | [agent.py](agent.py) |
| Tests (`.venv/Scripts/python -m pytest tests`) | [tests/test_moteur.py](tests/test_moteur.py) |
| Appel au modèle via la passerelle de l'équipe | [appel_modele.py](appel_modele.py) |
| Journal d'observabilité | [journal.py](journal.py) |
| Graphe de connaissances (joueurs, lieux, rôles, soupçons) | [graphe.py](graphe.py) |
| Lecture du journal, en direct ou après coup | [voir_trace.py](voir_trace.py) |

## Cheminement d'un message

```
serveur ──► client.reader ──► journal.perceive ──► abonnés (graphe.observe)
                 │
                 ▼  Inbox (garde le dernier scan, se vide à chaque snapshot)
           client.decisions ──► journal.handled ──► Explorer.decide
                                                        │  journal.why(...)
                                                        ▼
serveur ◄── client.send ◄── journal.act ◄───────────────┘
```

- Un message passe par `journal.perceive` dès sa réception, avant le tri de l'`Inbox`.
- `journal.handled` marque ce que l'agent a réellement traité.
- La lecture réseau ne doit jamais attendre une décision : un appel au modèle passe par `asyncio.to_thread`.

## Observabilité

Chaque lancement écrit `traces/<lancement>.jsonl`, une ligne JSON par événement, ainsi que `traces/<lancement>.graphe.json`. Le dossier `traces/` n'est pas versionné, car il contient les paroles des autres joueurs.

Chaque ligne porte `n`, `t`, `run` et `ev`. Les valeurs de `ev` :

| `ev` | Contenu |
|---|---|
| `in` | Message reçu : `type`, `seq`, `server_ms`, `data`. Au plus un `scan` par seconde est journalisé. |
| `handled` | Message transmis à `decide` |
| `out` | Commande envoyée : `type`, `command_id`, `data` |
| `why` | Raison d'une décision : `decision`, plus le contexte |
| `llm`, `llm_error` | Appel au modèle : prompt, réponse, `usage`, latence |
| `state` | Mémoire interne de l'agent, toutes les 15 s |
| `session` | Démarrage, connexion, déconnexion |

**Dans le code de l'agent :**
- `journal.why("turn", reason="obstacle", front_m=1.2)` : expliquer chaque nouvelle décision. C'est ce qui permet de comprendre une partie après coup.
- `journal.recent(ev="in", type="sound", since_s=60)` : derniers événements, en mémoire vive.
- `journal.subscribe(fn)` : recevoir chaque événement en direct.
- `self.graphe` (dans `Explorer`) : l'état courant du graphe. `self.graphe.resume()` en donne un texte court, prêt pour un prompt.

**En ligne de commande :**
- `python voir_trace.py --suivre` : fil de la partie en direct, depuis un autre terminal, sans connexion au serveur.
- `python voir_trace.py [fichier] --cypher` : résumé d'un lancement, graphe JSON et script Neo4j.
- `python graphe.py traces/X.jsonl` : recalcule le graphe à partir d'un journal.

Variables d'environnement : `TRACE=0` (pas de fichier), `TRACE_DIR`, `TRACE_SCAN_S`, `TRACE_MEMOIRE`.

**Lire les journaux sans saturer la mémoire.** Les lignes `vision` et `snapshot` sont longues. Extrayez des champs avec `jq` et coupez la sortie avec `| cut -c1-200`. Ne chargez jamais un journal entier dans le contexte.

## Graphe de connaissances

| Nœuds | Arêtes (poids entre 0 et 1, avec les preuves = `n` des lignes du journal) |
|---|---|
| `Joueur`, `Lieu`, `Role`, `Silhouette` (loup transformé anonyme) | `HABITE`, `EST_MORT_A`, `A_LE_ROLE` (certain), `SOUPCONNE_ETRE` (p loup), `PRETEND_ETRE`, `VU_PRES_DE`, `ACCUSE`, `A_VOTE_CONTRE` |

- **Recalculable** : le graphe se déduit uniquement du journal. Pour changer une règle, modifiez `graphe.py` et recalculez à partir d'anciens journaux.
- **Soupçons** : log-cote à partir d'un a priori de 25 %, plus les indices de `POIDS`. Un rôle certain écrase la probabilité.
- **Pas de position absolue** dans le protocole : une personne est rattachée au repère visible le plus proche au même instant.
- **D'une manche à l'autre**, rôles, soupçons et morts sont archivés ; `HABITE` et `VU_PRES_DE` sont conservés.
- **À vérifier sur une vraie manche** : le format exact de `vote_closed` et `dawn` est deviné dans `_vote_clos` et `_aube`.

## Moteur de règles

Les règles C1-C9 (communes), V1-V12 (village) et L1-L13 (loup) de l'étude sont appliquées sans modèle par `moteur.py`. Chaque décision est journalisée avec son numéro : `jq 'select(.ev=="why") | [.decision, .regle, .motif]'`.

- **Où aller** : `moteur.objectif()` (nuit à la maison, épreuve, conseil, pierre et chasse pour le loup).
- **Qui viser** : `choisir_vote`, `choisir_inspection`, `choisir_potion`, `choisir_successeur`, à partir des soupçons du graphe.
- **Quoi dire** : `Moteur.entendre` (réponses), `Moteur.au_conseil` (faits observés), toujours filtré par `nettoyer` (240 caractères, aucun secret, mots interdits du loup).
- **Le modèle** n'est appelé que pour départager un vote incertain, reformuler une réponse quand on est interpellé, et les épreuves que `epreuves.py` ne reconnaît pas. Sans `--model`, l'agent joue entièrement en local.
- **Limite connue** : le corps de `agent.py` ne sait se diriger que vers un repère visible ; sinon il explore au hasard. Le corps de la branche `romain` (`village/body.py`, navigation sur carte) pourrait exécuter les mêmes objectifs.
- **Pas implémentées** : L2 (rester loin des autres la nuit), L12 (réponse fausse du loup aux épreuves, tant qu'on ne sait pas si les réponses sont visibles) et L13 (estimer les rôles chaque matin). V3 et V12 ne sont que des poids du graphe.
- **Horloge** : `graphe.minute` avance seule entre deux messages (`cycle_ms`) et se recale sur `nightfall` / `village_wakes`.

## Conventions

- Code, commentaires et commits en français, avec les accents.
- Ne versionnez jamais `.env`, qui contient `TEAM_TOKEN`. Le journal masque les clés `authorization`, `token` et `api_key`.
- Les appels au modèle coûtent du crédit : la marche et les délais se traitent localement, et seuls les choix (votes, épreuves) vont au modèle.
