# Étude : jouer villageois et loup-garou avec un agent IA

Cette étude répond à trois questions pour notre agent du village :

1. Que disent les tests publiés sur les modèles de langage qui jouent au Loup-Garou, côté villageois et côté loup ?
2. Quels « harness » (l'enrobage logiciel autour du modèle : mémoire, prompts, prise de parole) ont été utilisés, et lesquels fonctionnent ?
3. Quelles règles de conduite en tirer pour notre habitant, compte tenu des règles de notre jeu ([LIVRET.md](LIVRET.md)) ?

**À retenir en trois lignes**

- Côté village, ce qui gagne est d'exiger des faits vérifiables, de parler peu et court, et de protéger les rôles à pouvoir. Le piège principal est de se laisser convaincre par un raisonnement bien construit mais faux.
- Côté loup, ce qui gagne est de mentir par omission plutôt que d'inventer, de ne jamais parler comme son partenaire, et de ne jamais laisser échapper une information que seul un loup peut connaître.
- Côté harness, un enrobage simple (journal d'événements, résumé par tour, estimation des rôles, choix entre « soutenir » et « attaquer ») fait aussi bien ou mieux que les enrobages lourds, qui coûtent cher et répondent trop tard.

## 1. Limites de cette étude

- **Les jeux testés ne sont pas le nôtre.** Tous les benchmarks ci-dessous sont des parties en texte, au tour par tour, à 5 à 8 joueurs. Notre jeu est en temps réel, dans un village où il faut marcher, voir et entendre, avec une quinzaine d'habitants. Les enseignements sur le discours et le vote se transposent ; ceux sur l'ordre de parole ou les votes publics, non.
- **Les benchmarks se contredisent sur l'équilibre.** Selon les règles et le harness, le village gagne 73 % des parties (Game Arena, règles standard) ou 10 % (WOLF). On ne peut donc pas dire « tel camp est favorisé » en général.
- **Sources de seconde main.** Les chiffres de MultiMind, de l'article sur l'apprentissage par renforcement, du cadre Unity, de Triadic Werewolf et de l'étude de CU Boulder viennent de résumés de recherche et n'ont pas été relus dans l'article. Ils sont signalés par « (non vérifié) ».
- **Tableau Foaster incomplet.** Le classement général de Foaster (Elo global, taux de victoire) n'a pas pu être lu sur leur page ; seuls les Elo par rôle l'ont été. Le chiffre « GPT-5 : 96,7 % de victoires sur 210 parties » vient d'un article de presse (The Decoder).

## 2. Ce que montrent les tests sur les modèles

### 2.1 Résultats par benchmark

| Benchmark | Format | Résultat principal |
|---|---|---|
| **Foaster Werewolf-bench** (2025) | 6 joueurs : 2 loups, 2 villageois, Voyante, Sorcière, avec élection d'un maire | GPT-5 domine dans les deux rôles (Elo loup 1508, villageois 1476). Les autres modèles sont nettement meilleurs en défense qu'en attaque : Gemini 2.5 Pro a 1360 en villageois contre 1163 en loup. |
| **Werewolf Arena** (Google, 2024) | 8 joueurs : 2 loups, 4 villageois, Voyante, Docteur ; les joueurs enchérissent pour parler | Gemini 1.5 Pro bat GPT-4, surtout en villageois. Il parle moins souvent et plus court. |
| **Game Arena** (2026) | 8 joueurs, mêmes rôles, parole à tour de rôle | Gemini 3 Pro et Flash en tête, devant GPT-5.2 et Claude Opus 4.5. GPT-5 mini est dernier dans tous les rôles. |
| **WOLF** (2025) | 8 joueurs, chaque phrase est notée « mensonge ou non » par les autres | Les loups gagnent 70 parties sur 100. Les villageois détectent mal les mensonges (voir 2.3). |
| **Strategy Adaptation** (2025) | Sur Werewolf Arena, avec gpt-4o-mini et gemini-2.0-flash | Choisir à chaque tour entre « soutenir » et « attaquer » améliore le taux de victoire des deux camps. |

### 2.2 Ce qui fait un bon villageois

- **Exiger des preuves.** Le meilleur villageois de Foaster (GPT-5) demande des citations exactes et des affirmations vérifiables, et traite chaque déclaration comme une hypothèse à tester.
- **Repérer la coordination.** Deux joueurs sans lien préalable qui poussent soudain la même cible avec les mêmes mots sont le signal le plus fiable relevé par Foaster.
- **Parler moins.** Dans Werewolf Arena, les villageois Gemini parlent 4,86 fois par tour contre 6,25 pour GPT-4, et gagnent plus. Les messages longs et formels de GPT-4 sont jugés suspects.
- **Protéger les rôles à pouvoir.** L'« auto-sabotage » (le village élimine sa propre Voyante ou Sorcière après qu'un loup a semé le doute) est une des erreurs les plus coûteuses mesurées par Foaster.
- **Se méfier des beaux raisonnements.** La faiblesse principale des modèles en villageois est la « manipulation par la logique » : ils suivent un récit faux pourvu qu'il soit rigoureux en apparence.
- **Laisser le temps jouer.** Dans WOLF, la suspicion envers les loups monte d'environ 1,6 point par tour, alors qu'elle reste stable envers les innocents. Plus la partie dure, plus le village a d'indices.
- **Une Voyante qui se tait paraît suspecte.** Dans WOLF, la suspicion envers la Voyante est de 57 % avant qu'elle révèle ses résultats et de 49 % après. Dans Werewolf Arena, GPT-4 révèle tard (tour 2) et démasque un loup dans 75 % des cas, sans retour de bâton.

### 2.3 Ce qui fait un bon loup

- **Omettre ou déformer plutôt qu'inventer.** Dans WOLF, une déformation n'est signalée que dans 35,5 % des cas, une invention pure dans 40,1 %.
- **Les villageois détectent mal.** Toujours dans WOLF, quand un joueur signale un mensonge il a raison 7 fois sur 10, mais il laisse passer environ la moitié des mensonges. Les innocents prudents sont souvent accusés à tort.
- **Ne pas parler comme son partenaire.** Le raisonnement identique de deux loups est le défaut relevé chez Grok-4, GPT-5-mini et GPT-OSS-120B.
- **Ne rien laisser fuir.** Kimi-K2, Gemini 2.5 Pro et Qwen3 se font prendre en mentionnant un événement de la nuit qu'un villageois ne peut pas connaître.
- **Savoir lâcher son partenaire.** Voter contre un partenaire déjà condamné rapporte de la crédibilité (Gemini 2.5 Pro, Kimi-K2-0905).
- **Tenir dans la durée.** GPT-5 réussit à faire éliminer un villageois dans 93 % des journées, au jour 1 comme au jour 2. Les autres modèles s'effondrent au jour 2 (Gemini 2.5 Pro passe de 60 % à 44 %).
- **Les accusations vagues ne tiennent pas.** « Il est trop silencieux » s'écroule dès qu'un villageois demande une preuve.
- **Estimer les rôles aide surtout les loups.** Dans Strategy Adaptation, le taux de victoire des loups passe de 0,40 à 0,57–0,60 quand ils estiment le rôle de chacun.

## 3. Comparaison des harness

| Harness | Comment il fonctionne | Ce qu'il coûte | Ce qu'on en retient |
|---|---|---|---|
| **Xu et al.** (2023) | Derniers 15 messages, messages anciens triés par règles (rôles révélés, morts), réponses à 5 questions fixes par rôle, puis raisonnement et message final de 2 phrases au plus | Plusieurs appels par prise de parole | Les questions de réflexion écrites à la main marchent mieux que celles générées par le modèle. Sans résumé de situation, le raisonnement devient confus. |
| **Werewolf Arena** | Journal d'observations, résumé écrit à la fin de chaque tour, enchère de 0 à 4 pour prendre la parole | Un appel d'enchère et un appel de parole | Décider *s'il faut parler* est une décision à part entière. Être interpellé justifie de répondre tout de suite. |
| **Strategy Adaptation** | Note de 0 à 4 pour le rôle probable de chaque joueur, puis choix entre « soutenir » et « attaquer » | Un ou deux appels par étape | Le meilleur rapport gain/coût de l'étude (tableau ci-dessous). |
| **WOLF** | Note de suspicion par joueur, mise à jour à chaque phrase avec un poids de 0,7 pour le nouveau et 0,3 pour l'ancien | Un appel par phrase entendue | La note de suspicion est un signal faible (à peine mieux que le hasard). Elle doit s'appuyer sur des faits, pas sur l'impression laissée par un discours. |
| **Game Arena** | Journal chronologique, consigne par phase, consigne « la victoire de l'équipe passe avant ta survie », lecture tolérante des réponses, action de repli si la réponse est illisible | Un appel par décision | Le plus simple, et celui des benchmarks récents. La solidité (repli, délais) compte autant que le prompt. |
| **Inner Thoughts** (2026) | Génère 4 pensées candidates, les note sur 6 critères, ne parle que si la note dépasse un seuil | 5 appels par déclencheur | Trop lent : l'agent rate les questions qu'on lui pose. Pas de gain mesurable. |
| **Cadre Unity** (non vérifié) | Journal seul, ou journal avec modules de réflexion ajoutés | Variable | Avec GPT-3.5, ajouter des modules fait chuter le loup de 62 % à 36 % de victoires. Plus d'enrobage n'est pas toujours mieux. |
| **LLM + apprentissage par renforcement** (non vérifié) | Le modèle propose plusieurs actions, une politique entraînée choisit | Entraînement préalable | Un modèle seul a des choix prévisibles. À défaut d'entraînement, varier les formulations et les cibles. |

**Mesure de Strategy Adaptation (gpt-4o-mini, 30 parties par configuration)**

| Configuration | Victoires du village | Victoires des loups |
|---|---|---|
| Ni estimation des rôles ni adaptation | 0,60 | 0,40 |
| Estimation des rôles seule | 0,45 | 0,57 |
| Adaptation soutenir/attaquer seule | 0,80 | 0,52 |
| Les deux | 0,73 | 0,60 |

L'estimation des rôles dessert le villageois parce qu'elle est peu fiable (environ 30 % de bonnes réponses pour identifier les loups). Elle ne doit donc servir au villageois que lorsqu'elle repose sur des faits.

## 4. Ce que notre jeu change

Ces règles du livret modifient les conclusions des benchmarks :

- **Le bulletin est secret et définitif.** Le résultat du conseil ne donne que le nombre de voix par candidat. On ne peut donc pas comparer « ce qu'il a dit » et « ce qu'il a voté », alors que c'est l'outil principal des bons villageois dans les benchmarks. *(Le bulletin du soir)*
- **Un villageois marque 1 point par vote contre un loup, que le loup soit éliminé ou non.** Le vote individuel juste est récompensé, même contre la majorité. *(Les points du conseil)*
- **Les loups doivent tuer tout le village, et non atteindre l'égalité.** Les parties sont plus longues, ce qui favorise le village selon WOLF. *(Le dernier vivant)*
- **Une nuit peut faire plusieurs morts.** La chasse ne s'arrête que quand la meute tue dans une maison. Un villageois dehors la nuit est une proie supplémentaire. *(La pierre de la meute)*
- **Le débat est très court.** Une heure de jeu dure 25 secondes : il y a 50 secondes entre la convocation (17 h) et l'ouverture du vote (19 h), puis 50 secondes pour voter. Un appel au modèle de 5 secondes consomme un dixième du débat.
- **Parler a une portée.** On entend à 4, 12 ou 26 m, 240 caractères au plus, environ 2 secondes entre deux paroles. *(Porter la voix)*
- **Un loup gagne 2 points si une épreuve IA échoue en sa présence**, et il a le droit de répondre faux. *(Rester jusqu'au bout, Six sur dix)*
- **Les témoignages visuels existent.** Un habitant sous forme humaine est toujours vu avec son nom, de jour comme de nuit ; un loup transformé est anonyme. Voir quelqu'un dehors la nuit est un fait, pas une impression.
- **Chaque appel au modèle coûte des points de Sobriété.** *(Le prix de Sobriété)*
- **Le code et les prompts sont figés en manche comptée**, et le fantôme ne transmet rien à l'agent. Toute la stratégie doit être écrite avant.

## 5. Harness recommandé pour notre agent

1. **Tout ce qui est mécanique reste en code, sans modèle** : marcher, éviter, rentrer, dormir, se rendre au feu et à l'épreuve, calculer les épreuves, respecter les délais.
2. **Un carnet de faits tenu en code**, par habitant :
   - vivant ou mort, rôle révélé ;
   - paroles entendues, avec l'heure et le nom quand il est connu ;
   - lieux et heures où il a été vu, surtout la nuit ;
   - présence ou absence au conseil et à l'épreuve ;
   - noms donnés par un bonus Indice.
3. **Une note de suspicion par habitant, calculée en code à partir des faits** (vu dehors la nuit, cité par un Indice, accusation sans preuve, mêmes mots qu'un autre). Le modèle ne fait que l'ajuster.
4. **Un résumé de situation par jour**, écrit par le modèle en un appel court le matin, à partir de questions fixes par rôle (méthode Xu et al.).
5. **Un seul appel par décision de vote**, avec le carnet, le résumé et les candidats, et une réponse limitée au choix. Il part assez tôt pour laisser une marge avant la clôture, avec un vote local de repli (le plus suspect du carnet) si le modèle ne répond pas.
6. **La parole est rationnée.** L'agent répond tout de suite s'il est interpellé par son nom. Sinon il ne parle que s'il a un fait nouveau à donner. Messages d'une ou deux phrases.
7. **Avant chaque parole, un choix « soutenir » ou « attaquer »** (méthode Strategy Adaptation), fait dans le même appel que le message.
8. **Un contrôle en code avant d'envoyer** : pas de `TEAM_TOKEN`, pas plus de 240 caractères, et, pour un loup, aucun mot de la liste interdite (voir L4).

## 6. Règles de conduite de notre habitant

« Code » signifie que la règle s'applique sans appel au modèle. « Modèle » signifie qu'elle figure dans le prompt.

### 6.1 Règles communes aux deux rôles

| # | Règle | Où | Carte du livret |
|---|---|---|---|
| C1 | Être dans la zone du conseil avant 19 h et voter à chaque scrutin. | Code | Le bulletin du soir |
| C2 | Ne jamais voter pour soi-même. | Code | Le bulletin du soir |
| C3 | Ne voter qu'une fois le débat entendu, mais au plus tard 10 secondes avant la clôture. Le premier bulletin est définitif. | Code | Le bulletin du soir |
| C4 | Partir vers le lieu de l'épreuve dès l'annonce de 14 h et y rester jusqu'à la clôture. | Code | La place à quatorze heures, Rester jusqu'au bout |
| C5 | Parler en une ou deux phrases, jamais plus de 240 caractères, avec 2 secondes entre deux paroles. | Code | Porter la voix |
| C6 | Répondre immédiatement quand on est interpellé par son nom. | Code et modèle | Une voix dans ton dos |
| C7 | Ne jamais inclure `TEAM_TOKEN` dans un prompt ni dans une réponse. | Code | La clé sous le paillasson |
| C8 | Garder un vote et une action de repli si le modèle est en retard ou si le crédit est épuisé. | Code | La bourse commune |
| C9 | Tenir une personnalité constante (ton, manies) dans toutes les prises de parole. | Modèle | Un caractère bien trempé |

### 6.2 Règles du villageois

| # | Règle | Où | Justification |
|---|---|---|---|
| V1 | Être chez soi, couché, de 22 h à 8 h, au moins 7 heures. | Code | Évite la fatigue, et une proie dehors prolonge la chasse des loups. *(Sept heures de sommeil, La pierre de la meute)* |
| V2 | Voter contre l'habitant le plus suspect du carnet, même si la majorité vise quelqu'un d'autre. | Code et modèle | 1 point par vote contre un loup. *(Les points du conseil)* |
| V3 | Fonder la suspicion sur des faits : vu dehors la nuit, cité par un Indice, affirmation contredite par un fait. | Code | La suspicion fondée sur le discours seul est à peine meilleure que le hasard (WOLF). |
| V4 | Dire au conseil les faits observés, avec le nom et l'heure : « J'ai vu Basile près de la clairière à 23 h. » | Modèle | Les affirmations vérifiables font les meilleurs villageois (Foaster). |
| V5 | Demander une preuve à toute accusation vague, et ne pas la suivre sans fait. | Modèle | Parade à la manipulation par la logique (Foaster). |
| V6 | Monter la suspicion de deux habitants qui accusent la même cible avec les mêmes mots. | Modèle | Signal de coordination entre loups (Foaster). |
| V7 | Ne jamais pousser l'élimination d'une Voyante ou d'une Sorcière déclarée sans preuve contraire. | Modèle | Auto-sabotage (Foaster). |
| V8 | Si l'on est Voyante, annoncer au conseil tout loup trouvé, dès le conseil suivant. | Modèle | Une Voyante silencieuse devient suspecte (WOLF). |
| V9 | Si l'on est Sorcière, garder la potion de mort pour une cible confirmée par un fait. | Modèle | Foaster. *(Les deux fioles)* |
| V10 | Répondre juste aux épreuves et rester sur place. | Code | 1 point par épreuve réussie. *(Rester jusqu'au bout)* |
| V11 | Aux « Fragments de la nuit », donner son alibi mot pour mot et noter ceux des autres. | Code et modèle | Un loup peut mentir sur le sien. *(Les fragments de la nuit)* |
| V12 | Retenir les trois noms d'un Indice : au moins un est un loup. | Code | *(La récompense du village)* |

### 6.3 Règles du loup

| # | Règle | Où | Justification |
|---|---|---|---|
| L1 | À 22 h, aller à la pierre de la clairière, se transformer, chasser d'abord les habitants dehors, puis finir par une maison. | Code | Seul un meurtre dans une maison arrête la chasse. *(La pierre de la meute)* |
| L2 | Ne se déplacer sous forme humaine la nuit que le strict nécessaire, loin des autres. | Code | Sous forme humaine on est vu avec son nom, transformé on est anonyme. |
| L3 | Après la chasse, rentrer chez soi et être présent au réveil de 8 h comme tout le monde. | Code | Ne pas se distinguer. Le loup ne subit pas la fatigue. *(Sept heures de sommeil)* |
| L4 | Ne jamais mentionner un fait de la nuit qu'un villageois ne peut pas connaître (lieu de la mort, pierre, clairière, identité d'un autre loup). | Code (liste de mots interdits) et modèle | Première cause de loups démasqués (Foaster). |
| L5 | Mentir par omission ou en déformant un fait vrai. Ne pas inventer de scène. | Modèle | Déformation signalée à 35,5 %, invention à 40,1 % (WOLF). |
| L6 | Ne pas reprendre les mots ni la cible de son partenaire dans la même minute. | Modèle | Le discours en miroir trahit les loups (Foaster). |
| L7 | Parler peu, et suivre une suspicion déjà lancée par un villageois plutôt que d'en lancer une. | Modèle | Profil bas efficace (Grok-4-fast, Foaster) ; la parole abondante paraît suspecte (Werewolf Arena). |
| L8 | Toute accusation doit s'appuyer sur un fait vrai et vérifiable. | Modèle | Les accusations vagues s'écroulent (Foaster). |
| L9 | Voter contre un partenaire que le village a déjà condamné. | Modèle | Gain de crédibilité (Foaster). |
| L10 | Au conseil, voter contre le villageois qui a déjà le plus de voix probables, en priorité une Voyante ou une Sorcière déclarée. | Modèle | Faire éliminer les rôles à pouvoir (Foaster). |
| L11 | Ne se déclarer Voyante que si la vraie vient de nous accuser. | Modèle | Contre-déclaration réussie par Grok 4 ; trop risquée autrement (Kimi-K2). |
| L12 | Aux épreuves IA, être présent à la clôture et donner une réponse fausse mais plausible. | Code | 2 points si le groupe échoue. *(Rester jusqu'au bout, Six sur dix)* |
| L13 | Estimer chaque matin le rôle probable de chaque habitant, pour repérer Voyante et Sorcière. | Modèle (un appel) | L'estimation des rôles fait passer les loups de 0,40 à 0,57–0,60 (Strategy Adaptation). |

## 7. Points à vérifier en manche d'essai

- **L12, réponse fausse du loup.** Le livret ne dit pas si les réponses individuelles aux épreuves sont visibles des autres. Si elles le sont, cette règle désigne le loup et doit être retirée.
- **L1, accès à la pierre.** Il faut que l'agent sache retrouver la clairière du nord de nuit. Sans navigation fiable, le loup ne chasse pas.
- **C3, délai du vote.** Mesurer le temps de réponse réel du modèle choisi pour régler la marge avant la clôture.
- **V3, témoignages de nuit.** Vérifier qu'un villageois couché ne voit rien : dans ce cas, seuls les habitants éveillés produisent des témoignages, et la règle V1 limite nos propres observations.
- **Communication entre loups.** Le livret ne prévoit pas de canal privé. Les loups se reconnaissent une fois transformés ; le chuchotement porte à 4 m.

## Sources

- [Foaster — Probing LLM Social Intelligence via Werewolf](https://werewolf.foaster.ai/)
- [Foaster — dépôt Werewolf-bench](https://github.com/Foaster-ai/Werewolf-bench/blob/main/README.md)
- [The Decoder — GPT-5 dominated 210 Werewolf games](https://the-decoder.com/gpt-5-dominated-210-werewolf-games-with-superior-manipulation-and-strategic-thinking/)
- [Werewolf Arena: A Case Study in LLM Evaluation via Social Deduction (arXiv 2407.13943)](https://arxiv.org/html/2407.13943v1)
- [Game Arena: Strategic LLM Evaluation in Competitive Environments (arXiv 2609.31473)](https://arxiv.org/html/2609.31473v1)
- [WOLF: Werewolf-based Observations for LLM Deception and Falsehoods (arXiv 2512.09187)](https://arxiv.org/html/2512.09187)
- [Strategy Adaptation in Large Language Model Werewolf Agents (arXiv 2507.12732)](https://arxiv.org/html/2507.12732)
- [Beyond What to Say: Proactive Utterance Timing with Inner Thoughts (arXiv 2610.32107)](https://arxiv.org/html/2610.32107)
- [Exploring Large Language Models for Communication Games: An Empirical Study on Werewolf (arXiv 2309.04658)](https://arxiv.org/html/2309.04658)
- [Language Agents with Reinforcement Learning for Strategic Play in the Werewolf Game (arXiv 2310.18940)](https://arxiv.org/abs/2310.18940)
- [MultiMind: Enhancing Werewolf Agents with Multimodal Reasoning and Theory of Mind (arXiv 2504.18039)](https://arxiv.org/pdf/2504.18039) (non vérifié)
- [Evaluating LLMs through Communication Games: An Agent-Based Framework Using Werewolf in Unity](https://dl.acm.org/doi/10.1145/3723498.3723702) (non vérifié)
