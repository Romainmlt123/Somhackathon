# Données de jeu récoltées (26 novembre, soirée)

Récoltées par l'agent de Romain, version `romain-hugues`, dans le vrai village (habitant Cédric).

| Dossier | Contenu | Comment le lire |
|---|---|---|
| `traces/*.jsonl` | Journal d'observabilité : messages reçus (`in`), traités (`handled`), commandes (`out`), raisons (`why`), appels au modèle (`llm`), état (`state`) | `python voir_trace.py donnees_jeu/traces/<fichier>.jsonl` |
| `traces/*.graphe.json` | Graphe de connaissances reconstruit à partir du journal (qui a vu quoi, soupçons) | `graphe.py` |
| `decisions/agent-*.jsonl` | Chaque décision du cerveau : contexte envoyé, réponse, action, résultat, coût | JSON lignes |
| `logs/` | Sorties lisibles de l'agent (pensées, actions, paroles) | texte |
| `../data/village_map.json` | Carte des repères fixes du village (repère de l'équipe) | utilisée par l'agent |

Les messages réseau bruts (plusieurs Mo) ne sont pas poussés.
La valeur du jeton d'équipe n'apparaît dans aucun de ces fichiers (vérifié avant le push).

## Ce qu'on y voit (vrai jeu)
- Trois lancements successifs de l'agent, avec deux modèles : `gemini-4-hydrogen` (réponses coupées à 260 puis 800 jetons) puis `gemini-4-argon` (sans limite, réflexion « minimal »).
- Une manche comptée complète : élection du Capitaine, votes du conseil (`why` avec `decision: vote`, `source: moteur`), nuit, aube avec mort, mémos du matin.
- La pierre des loups n'a pas été trouvée : cherchée autour de la chapelle, de la cantine, à l'ouest et à l'est.
