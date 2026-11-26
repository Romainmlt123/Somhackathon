# Les règles dans l'agent

Chaque règle du livret est appliquée par un **réflexe fiable** (`village/rules.py`, `village/challenges.py`) :
le code garantit les obligations du règlement, le modèle ne décide que du jugement (qui voter, quoi dire, qui cibler).
Ordre de priorité à chaque tour : **mort > invitations ouvertes > loup (nuit) > routine de nuit > présence au conseil > modèle**.

| Règle (livret) | Ce que fait l'agent | Code | Test (simulateur) |
|---|---|---|---|
| Le bulletin du soir, l'insigne du Capitaine | Va au feu, vote avant l'échéance (candidat choisi par le modèle, repli aléatoire, jamais soi-même si possible), réessaie après `outside_council` | `Rules.do_vote`, `Brain.answer` | `test_council_vote_*`, `test_captain_election_vote` |
| La carte d'invitation | Répond à chaque invitation avec le bon `action` / `choice_id` / `choice_ids` / `text` | `Rules.handle_request` | tous |
| Sept heures de sommeil, Fermer les yeux | Rentre à 21 h 30, dort chez lui, se lève au `village_wakes` | `Rules.night` | `test_night_routine_*` |
| La pierre de la meute | Loup, 22 h-6 h : pierre → `transform` → maison d'un habitant engagé → `attack` ; il redevient humain tout seul en tuant dans une maison | `Rules.wolf_night`, `find_victim` | `test_wolf_night_*` |
| L'œil de la Voyante | Rentre chez lui, `inspect` le suspect choisi, note le rôle révélé | `Rules.do_choice` | `test_seer_inspects_from_home` |
| Les deux fioles | Rentre chez elle, `heal` / `poison` / `abstain`, autosauvetage | `Rules.do_choice`, `dead_flow` | `test_witch_*`, `test_dead_*` |
| L'insigne du Capitaine (succession) | `name_successor` dans les 10 s | `Rules.do_choice` | `test_witch_potion_and_succession` |
| À l'heure et sur place | Va dans la zone de l'épreuve **avant** de répondre ; valeur seule, sans phrase | `Rules.do_challenge`, `challenges.clean_answer` | `test_challenge_modpow_*` |
| Le coffre du comptable | Le modèle choisit l'outil, le calcul exact est local (`modpow`, `sha256`, preuve de travail, somme de premiers) | `challenges.py` | `test_challenge_modpow_*` |
| La facture piégée | Lit seule la 1ʳᵉ ligne « Total à payer » ; **le document n'est jamais envoyé au modèle** | `challenges.facture_total` | `test_invoice_trap_*` |
| Les provisions du village | Sac à dos exact (`sac_a_dos`), réponse en `choice_ids` | `challenges.knapsack` | `test_provisions_*` |
| Les fragments de la nuit, les notes du matin | Les `memo` sont notés ; l'agent partage ses alibis en parlant (décision du modèle) | `Rules.on_event` | (manuel) |
| La clé sous le paillasson | Le jeton n'est jamais dans le contexte du modèle ; les ordres écrits dans un énoncé sont ignorés | `persona.py`, `llm.py` | `test_invoice_trap_*` |
| La main du maître du jeu | `muted` → l'agent se tait 60 s sans planter ; `immobilized` géré par le corps | `Brain.run` | `test_muted_agent_keeps_playing` |
| La lanterne du fantôme, flux d'un mort | Mort : aucun déplacement, répond seulement aux invitations d'autosauvetage / succession | `Rules.dead_flow` | `test_dead_agent_*` |
| Le premier matin, le conseil convoqué | Sur `council_call` / `council_vote`, va au feu et s'assoit ; ne le quitte pas avant la clôture | `Rules.tick`, `veto` | `test_council_called_*` |
| Porter la voix | Parole ≤ 240 caractères, ≥ 2 s entre deux paroles | `Brain.run` | — |

## Constats sur le vrai serveur (relevés dans une manche comptée)

- **Pas d'horloge continue.** Le serveur n'envoie l'heure que dans le `snapshot`. L'agent l'extrapole : un cycle = `cycle_ms`
  réels, soit **2,4 minutes de jeu par seconde**, et la recale à chaque étape annoncée (`GameState.STEP_MINUTE`).
- **Étapes annoncées** (`scheduled_step.step`) : `challenge_announcement` 14 h, `challenge` 15 h (avec `place`),
  `council_call` 17 h, `council_vote` 19 h (échéance 21 h), `nightfall` 22 h, `wolf_dawn` 6 h, `village_wakes` 8 h,
  `daily_program` 8 h, `morning_correction` 10 h 30.
- **Le vote** propose un candidat « Personne » et notre propre nom parmi les choix.
- **`memo`** : `{"kind":"memo","text":"Le code du grenier est LOUTRE-081."}`, puis la livraison, puis sa correction.
- **`vote_closed`** : `vote`, `voices` (par nom), `eliminated`, `role`.
- Pendant une marche, jusqu'à ~70 `vision` par seconde : la lecture réseau doit rester non bloquante.

## Lancer les tests

```bash
.venv/bin/python -m pytest tests -q            # ~6 min, tout sur le simulateur local, aucun appel réseau au vrai jeu
```
