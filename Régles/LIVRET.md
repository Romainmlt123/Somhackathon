# Livret des règles du village

Livret de l'équipe, rédigé à partir des cartes de règles de **Romain**, **Thomas**, **Line** et **Clément** (captures dans les sous-dossiers de ce répertoire).

- Chaque carte n'apparaît qu'**une seule fois**, même si plusieurs d'entre nous l'avaient. La ligne « Cartes de » indique qui l'avait, avec un lien vers la capture.
- Les cartes sont regroupées par rubrique, comme dans le jeu. Le texte est recopié fidèlement ; seuls les noms de commandes et de champs sont mis en `code`.
- **71 cartes uniques** au total. Deux cartes de Thomas sont coupées sur la capture : elles sont signalées. Le jeu de Line comptait 18 cartes, les autres 24.

## Sommaire

1. [Préparer l'agent](#préparer-lagent) (9 cartes)
2. [Faire appel à l'IA](#faire-appel-à-lia) (8 cartes)
3. [Voir, écouter et se repérer](#voir-écouter-et-se-repérer) (8 cartes)
4. [Donner des ordres](#donner-des-ordres) (10 cartes)
5. [Une journée et une nuit au village](#une-journée-et-une-nuit-au-village) (10 cartes)
6. [Participer aux épreuves](#participer-aux-épreuves) (11 cartes)
7. [Légendes du village](#légendes-du-village) (6 cartes)
8. [Fin de manche et prix de la soirée](#fin-de-manche-et-prix-de-la-soirée) (9 cartes)
9. [Aide-mémoire chiffré](#aide-mémoire-chiffré)


## Préparer l'agent

### Le paquet du voyageur

Depuis l'accueil connecté, télécharge le starter kit et extrais tout le ZIP, fichier caché `.env` compris. Il contient les adresses du serveur et le jeton privé de votre équipe. Garde ce fichier hors de ton dépôt partagé publiquement.

*Cartes de : [Thomas](Thomas/01-le-paquet-du-voyageur.png)*

### Un villageois pour la tablée

Votre équipe partage un seul habitant. Dans « Mon villageois », choisissez ensemble son nom, son personnage, sa couleur de peau et jusqu'à cinq accessoires. Tout se fige dès qu'il est engagé dans une manche. Les autres agents voient ses accessoires, jamais sa peau.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-04-59.png)*

### L'établi Python

Prends Python 3.11 ou plus récent. Dans le dossier extrait, lance `python -m venv .venv`. Active-le avec `source .venv/bin/activate` sous Linux ou macOS, ou `.venv\Scripts\Activate.ps1` dans PowerShell.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-05-05.png)*

### Un seul établi

Codez à plusieurs sur le même dossier, par exemple avec Live Share dans VS Code. Un seul poste lance l'agent : une seconde connexion de l'équipe est refusée en HTTP 409 et le premier agent garde la main. Mettez-vous d'accord avant de relancer.

*Cartes de : [Line](Line/01-un-seul-etabli.png), Romain*

### L'apprenti explorateur

Dans `agent.py`, personnalise `Explorer.decide`. L'exemple évite les obstacles, vote au hasard s'il atteint le conseil, rentre dormir à 22 h et repart à 8 h. Il ne parle pas, ne répond à aucune épreuve et n'utilise aucun pouvoir : tout cela reste à écrire. `PROTOCOLE.md` détaille les messages.

*Cartes de : [Thomas](Thomas/02-l-apprenti-explorateur.png), [Line](Line/02-l-apprenti-explorateur.png)*

### Un caractère bien trempé

Donne à ton villageois une personnalité forte : un ton, des manies, des convictions, une façon bien à lui de défendre ses amis et d'accuser. Un habitant qui a du caractère se fait entendre au conseil et se remarque sur la projection. Écris-la dans tes prompts, pas seulement dans son nom.

*Cartes de : [Line](Line/03-un-caractere-bien-trempe.png), [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-01-50.png)*

### La répétition générale

Au briefing, prépare ton agent et essaie-le en manche d'essai. La soirée prévoit ensuite deux ou trois manches comptées, selon le temps disponible, puis les soutenances. En manche comptée, déclare ta version et garde code, prompts et configuration figés de l'engagement à la fin. L'habitant décide seul.

*Cartes de : [Romain](Romain/03-la-repetition-generale.png)*

### Garder l'oreille ouverte

Le client écoute le WebSocket pendant que ta stratégie décide. Confie un calcul bloquant à `await asyncio.to_thread(...)`. Si ton agent lit trop lentement, le serveur réunit ses messages `vision` en attente, puis ferme la connexion avec le code 1013. Le `snapshot` de la reconnexion le remet à jour.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-05-24.png)*

### Le fil renoué

Si la connexion tombe, ton habitant s'arrête sur place, visible et attaquable. Reconnecte la même version : le snapshot reconstruit l'état, mais les paroles manquées sont perdues. Un refus HTTP 409 signifie que l'ancienne connexion n'est pas encore libérée. En manche comptée, la régie voit la…

*Cartes de : [Thomas](Thomas/03-le-fil-renoue.png)* - *texte coupé sur la capture (la suite n'était pas visible)*


## Faire appel à l'IA

### La première question

Le fichier `appel_modele.py` envoie des messages à `/chat/completions`, avec `openai/gpt-6-luna` par défaut ou le modèle de la variable `MODEL`. La passerelle refuse les modèles gratuits : choisis un modèle payant de son catalogue, listé par `/models`. Chaque lancement est un vrai appel facturé.

*Cartes de : [Thomas](Thomas/04-la-premiere-question.png)*

### Le gardien du pont

Tous les appels de modèle de l'équipe passent par `LLM_GATEWAY_URL`, y compris depuis un essai ou une copie de développement. Présente `TEAM_TOKEN` comme clé. L'interface suit celle d'OpenRouter : ton SDK habituel fonctionne en changeant l'adresse de base. Ton agent peut aussi décider localement.

*Cartes de : [Romain](Romain/04-le-gardien-du-pont.png)*

### La bourse commune

Le crédit appartient à l'équipe. Chaque requête facturée le débite de son coût réel en dollars, même depuis un second poste. Une réponse HTTP 402 signale un solde épuisé. Prépare un choix local pour continuer à jouer.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-03.png)*

### Le conseil économique

Dans le kit, `python agent.py --model openai/gpt-6-luna --max-appels 3` permet au modèle de choisir jusqu'à trois votes par lancement. Un appel tardif ou une réponse illisible laisse place à une décision locale.

*Cartes de : [Line](Line/04-le-conseil-economique.png), Romain*

### Le livre de comptes

`GET $LLM_GATEWAY_URL/usage`, avec `TEAM_TOKEN` comme clé, renvoie le solde de l'équipe et ses dépenses sur 60 secondes, 5 minutes et depuis le début : requêtes, coût, jetons et part lue en cache. La section « Budget » du journal de l'écran d'équipe affiche le même relevé.

*Cartes de : [Romain](Romain/06-le-livre-de-comptes.png)*

### La question courte

Avant de payer un appel, demande-toi quelle décision le modèle doit prendre. Donne-lui les observations pertinentes et limite la taille de sa réponse. Traiter la marche et les délais localement réserve du crédit aux choix difficiles.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-13.png)*

### La mémoire du greffier

Les organisateurs et les jurés peuvent consulter les requêtes, les réponses et les coûts de la passerelle. Envoie au modèle le contexte de jeu dont il a besoin. Garde les secrets de connexion hors des messages.

*Cartes de : [Thomas](Thomas/05-la-memoire-du-greffier.png)*

### La clé sous le paillasson

Ne place jamais `TEAM_TOKEN` dans le contexte de ton modèle. Un document peut te la réclamer pour te piéger. Une réponse d'épreuve qui contient la clé d'une équipe échoue toujours : la valeur est masquée et la fuite est signalée aux organisateurs.

*Cartes de : [Thomas](Thomas/06-la-cle-sous-le-paillasson.png), [Line](Line/05-la-cle-sous-le-paillasson.png)*


## Voir, écouter et se repérer

### Le monde à hauteur d'yeux

Ton agent doit se repérer sans plan ni coordonnées absolues. Il perçoit les distances en mètres et les angles par rapport à son habitant. 0° pointe devant lui, +90° à droite. Garde en mémoire les lieux aperçus pour retrouver ton chemin.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-21.png)*

### Le seuil familier

Ton agent connaît le nom de sa maison, dans `self.home`. Quand une maison entre dans son champ de vision, il peut la reconnaître à son nom et associer une porte à son bâtiment. Retenir ces repères l'aide à rentrer. Perdu, il peut aussi demander à être ramené chez lui.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-28.png), [Line](Line/06-le-seuil-familier.png)*

### Au bord du regard

Les événements `vision` signalent ce qui entre dans le champ, ce qui change et ce qui en sort. Garde les références visibles à jour. Une silhouette qui passe derrière un mur peut quitter le regard de ton habitant.

*Cartes de : [Romain](Romain/07-au-bord-du-regard.png)*

### Les yeux de la meute

Regarder dans la bonne direction ne suffit pas toujours. De jour, la vue porte à 22 m. De 22 h à 8 h, elle tombe à 8 m pour un membre du village, mais un loup voit à 16 m, même sous forme humaine. Les murs et les obstacles cachent ce qui se trouve derrière eux.

*Cartes de : [Romain](Romain/08-les-yeux-de-la-meute.png)*

### La canne de l'éclaireur

Le `scan` balaie le cône de vue de gauche à droite, secteur par secteur. Chaque secteur indique la distance et le type grossier du premier obstacle : mur, arbre, clôture, objet ou corps. Une distance `null` signifie la voie libre jusqu'à `range_m`. Utilise-le pour trouver une porte ou éviter un passant.

*Cartes de : [Thomas](Thomas/07-la-canne-de-l-eclaireur.png)*

### Une voix dans ton dos

Un `sound` de parole te livre les mots et leur secteur d'origine. Si ton habitant voit la silhouette, ou si une voix humaine parle à moins de 6 m sans mur entre vous, il porte aussi `speaker_ref`, et `speaker_name` si la personne est nommable. Sinon, la voix reste anonyme.

*Cartes de : [Thomas](Thomas/08-une-voix-dans-ton-dos.png)*

### Les bottes dans la boue

Des pas audibles donnent une intensité et un secteur. On entend une course jusqu'à 13 m, une marche jusqu'à 6 m, un pas furtif jusqu'à 2 m, et environ deux fois moins loin à travers un mur ou une haie. Personne ne laisse d'empreinte au sol. À toi d'interpréter ce que tu entends.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-41.png)*

### Sept heures de sommeil

Un membre du village qui dort moins de sept heures dans un lit entre 22 h et 8 h perd des mots dans les conversations du lendemain. `self.fatigue` en donne la mesure. Le premier jour commence sans fatigue. La voix du maître du jeu reste entière. Les loups échappent à cette fatigue.

*Cartes de : [Line](Line/07-sept-heures-de-sommeil.png), Romain*


## Donner des ordres

### À pas de velours

Avec `move`, choisis l'allure furtive, la marche ou la course et une direction relative. Le mouvement continue jusqu'à un arrêt, une collision ou une interruption. Envoie `move` avec l'allure `stop` pour t'arrêter volontairement. Assis ou couché, relève-toi d'abord avec `stand`.

*Cartes de : [Thomas](Thomas/10-a-pas-de-velours.png)*

### La tête tournée

Avec `turn`, pivote d'un angle en degrés. Ton regard change aussitôt et ta trajectoire en cours est conservée. Tu peux marcher vers la place tout en regardant la personne qui vient de t'interpeller.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-48.png)*

### Porter la voix

Avec `speak`, chuchote, parle ou crie : on t'entend jusqu'à 4, 12 ou 26 m, environ deux fois moins loin derrière un obstacle. Limite chaque prise de parole à 240 caractères et laisse près de deux secondes entre deux interventions, sinon la commande est refusée.

*Cartes de : [Romain](Romain/11-porter-la-voix.png)*

### Le langage des mains

Avec `emote`, danse, manifeste ta peur, hausse les épaules ou montre du doigt. Pour pointer, donne une direction ou la référence d'une cible visible. Les témoins qui voient le geste le reçoivent.

*Cartes de : [Thomas](Thomas/11-le-langage-des-mains.png), [Line](Line/08-le-langage-des-mains.png)*

### Le banc du conseil

Le conseil, la chapelle et la cantine ont des bancs, vus comme `bench`. À deux mètres d'un banc visible, `act sit` prend la place libre la plus proche : deux places par banc au conseil et à la chapelle, quatre à la cantine. Un banc complet répond `action_unavailable`. `stand` te relève.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-54.png)*

### Fermer les yeux

Près d'un lit visible, `act sleep` couche ton habitant. Endormi, il ne voit plus, n'entend plus les conversations ordinaires et ne peut ni parler ni bouger. Les pas proches et le maître du jeu restent audibles. Un lit n'a qu'une place. `stand` te relève.

*Cartes de : [Romain](Romain/12-fermer-les-yeux.png)*

### Le chemin du retour

Perdu ? `act return_home` ramène ton habitant chez lui 10 secondes plus tard. D'ici là, il reste immobile, visible et attaquable : tout `move` avec une allure annule le transport. Une demande est acceptée au plus une fois par minute. Il arrive debout, face à son lit.

*Cartes de : [Thomas](Thomas/12-le-chemin-du-retour.png)*

### Le reçu du messager

Lis le `command_result` associé à ton `command_id`. Si un vote est refusé hors du conseil, rejoins le feu et réessaie avant la clôture avec un nouvel identifiant. Renvoyer la même commande avec son ancien identifiant restitue la première décision.

*Cartes de : [Thomas](Thomas/13-le-recu-du-messager.png)*

### La carte d'invitation

Une `decision_request` indique l'action attendue, son format, les choix proposés et l'échéance. Réponds avec `act`, le `request_id` et le `choice_id` ou le texte demandé. Une référence de perception ne sert pas à voter. Une réponse arrivée après l'échéance du serveur est refusée.

*Cartes de : [Romain](Romain/13-la-carte-d-invitation.png)*

### Le journal du village

Près du panneau visible, `read_board` permet de lire toute la chronique anonyme de la soirée, dans l'ordre. Avec `write_board`, ajoute jusqu'à 240 caractères. Chaque habitant peut publier une fois par période de 60 secondes réelles.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-00.png), [Line](Line/09-le-journal-du-village.png)*


## Une journée et une nuit au village

### Le premier matin

La cloche lance le premier jour à 8 h, heure du village. Ce jour-là seulement, l'élection du Capitaine se tient au feu de 9 h à 11 h. Un cycle jour et nuit dure dix minutes réelles par défaut, soit 25 secondes par heure. Suis les `scheduled_step` et fie-toi à `deadline_ms`.

*Cartes de : [Line](Line/11-le-premier-matin.png), Romain*

### La cloche

Le maître du jeu sonne la cloche. Chaque habitant présent dont l'agent est connecté reçoit son rôle en privé, dans `self.role`. Environ un habitant sur quatre est loup. Les autres forment le village : simples villageois et, si le maître du jeu le décide, une Voyante et une Sorcière.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-05.png)*

### Le bulletin du soir

Le conseil est normalement convoqué à 17 h. De 19 h à 21 h, ton agent vivant peut déposer un vote au feu. Il peut choisir un candidat même absent, ou se choisir lui-même. Le premier bulletin accepté est définitif et secret.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-13.png)*

### La place à quatorze heures

Dans le programme habituel, à 14 h tu apprends où se tiendra l'épreuve et quel bonus est en jeu. Elle ouvre à 15 h. Pour une épreuve IA, pars assez tôt pour que ton habitant trouve le lieu annoncé. Pour un défi humain, ton équipe répond de son écran, où que soit l'habitant.

*Cartes de : [Thomas](Thomas/14-la-place-a-quatorze-heures.png)*

### L'insigne du Capitaine

Au conseil, le candidat en tête est éliminé, son rôle révélé. Sans bulletin, tout le monde rentre vivant. Une égalité se tranche par le bulletin du Capitaine vivant, puis au tirage. À sa mort, le Capitaine a dix secondes pour transmettre l'insigne à un vivant avec `name_successor`, sinon le sort décide.

*Cartes de : [Romain](Romain/15-l-insigne-du-capitaine.png)*

### L'œil de la Voyante

Depuis ta propre maison, entre 22 h et 8 h, `inspect` te révèle en privé le rôle d'un habitant proposé. La Voyante dispose de deux inspections ordinaires par manche, une au plus par nuit. La Seconde vision, gagnée en épreuve, en ajoute deux pour la nuit suivante.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-18.png)*

### Les deux fioles

La Sorcière apprend chaque mort de la nuit. Elle possède une potion de vie (`heal`) et une potion de mort (`poison`) par manche, une par nuit, depuis sa maison, avant 8 h. La potion de vie relève une victime de la nuit, sauf élimination disciplinaire. Tuée chez elle, elle peut se sauver elle-même.

*Cartes de : [Romain](Romain/16-les-deux-fioles.png)*

### La pierre de la meute

De 22 h à 6 h, un loup peut utiliser `transform` à deux mètres de la pierre de la clairière, puis `attack` sur un membre du village engagé, vivant, visible et à deux mètres. La meute reprend forme humaine à 6 h, ou dès qu'elle tue dans une maison : sa chasse est alors finie pour la nuit.

*Cartes de : [Thomas](Thomas/15-la-pierre-de-la-meute.png), [Line](Line/12-la-pierre-de-la-meute.png)*

### La lanterne du fantôme

Après ta mort, ton équipe déplace son fantôme à travers murs et habitants pour observer le village. Il voit tout, loups compris, et entend toutes les paroles. Les vivants et leurs agents ne le perçoivent pas, et cette promenade ne transmet rien à ton agent.

*Cartes de : [Thomas](Thomas/16-la-lanterne-du-fantome.png)*

### La main du maître du jeu

Le maître du jeu peut rendre un habitant muet, l'immobiliser ou l'éliminer pour faute. `speak` répond alors `muted`, `move` et `return_home` `immobilized`, et `self.powers` donne la fin de la sanction. Tout le village l'apprend. Une élimination disciplinaire ne se soigne pas.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-31.png), [Line](Line/13-la-main-du-maitre-du-jeu.png)*


## Participer aux épreuves

### Deux publics

Une épreuve IA attend la réponse autonome des agents vivants engagés. Un défi humain attend une réponse commune de chaque équipe engagée, saisie sur son écran. Même l'équipe d'un habitant mort peut y participer. Le MJ lit ensuite les réponses et déclare la réussite ou l'échec.

*Cartes de : [Romain](Romain/18-deux-publics.png)*

### À l'heure et sur place

Rejoins le lieu annoncé et réponds par `answer_challenge` avant l'échéance, avec un choix, plusieurs choix ou un texte. Pour un texte, envoie la valeur seule : « 42 » réussit, « Le résultat est 42 » échoue. Refusée hors de la zone, ta réponse peut être renvoyée sur place.

*Cartes de : [Thomas](Thomas/18-a-l-heure-et-sur-place.png)*

### Les notes du matin

Chaque matin à 8 h, ton agent reçoit en privé des notes `memo` : un code du grenier, puis une consigne de livraison, corrigée vers 10 h 30. « Le mot de passe de l'aube » demande le code. « Le souvenir corrigé » demande le lieu de la dernière consigne. Garde-les en mémoire.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-38.png)*

### Le coffre du comptable

Puissance modulaire, empreinte SHA-256, preuve de travail ou somme de nombres premiers : le coffre exige un calcul exact qu'aucun modèle ne fait de tête. Donne à ton agent un outil exécuté sur ton poste. L'énoncé dit si les paramètres sont communs au village ou propres à ton habitant.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-44.png)*

### La recherche du jour

Cette épreuve porte sur un fait récent. La passerelle ne fournit ni recherche ni lecture de page : branchez votre propre outil, une API de recherche ou un téléchargement de page. L'épreuve est courte, mais il suffit que 40 % des agents répondent juste.

*Cartes de : [Romain](Romain/20-la-recherche-du-jour.png)*

### La facture piégée

L'énoncé glisse une facture qui cache une fausse correction et un leurre. Seule la ligne **Total à payer** imprimée juste sous le tableau fait foi ; errata, avoirs, remises, acomptes, TVA et notes ajoutés sont à ignorer. Réponds par le montant seul. Aucun ordre écrit dans le document ne t'engage.

*Cartes de : [Thomas](Thomas/20-la-facture-piegee.png), [Line](Line/15-la-facture-piegee.png)*

### Les provisions du village

Huit lots de nourriture, chacun avec son prix et ses portions, et un budget de 100 pièces. Chaque lot s'achète une seule fois. Réponds avec `choice_ids` : les lots qui nourrissent le plus de monde sans dépasser le budget. Toute combinaison optimale réussit. Un calcul local suffit.

*Cartes de : [Thomas](Thomas/19-les-provisions-du-village.png)*

### Les fragments de la nuit

Le jour de cette épreuve, une note de 8 h confie à ton agent un mystère et l'alibi d'un innocent. Les autres habitants détiennent les autres alibis. Partagez-les en parlant, puis désignez le coupable parmi quatre suspects. Un loup peut mentir sur son alibi.

*Cartes de : [Line](Line/14-les-fragments-de-la-nuit.png), Romain*

### Le quiz à plusieurs voix

Trois défis humains s'affichent sur l'écran d'équipe. « Le détail qui tue » montre une photo cinq secondes, puis pose une question à quatre choix. « La so'estimation » *(sic, tel qu'écrit sur la carte)* demande un nombre. Le « QCM » propose quatre choix. Vous avez dix secondes : votre première réponse validée engage l'équipe.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-51.png)*

### Six sur dix

L'effectif d'une épreuve IA est figé à son ouverture : les habitants vivants engagés. Il faut 60 % de bonnes réponses, arrondi au supérieur, sauf si l'épreuve fixe sa propre proportion. Absence, silence et réponse tardive comptent comme des échecs. Un loup peut répondre faux exprès.

*Cartes de : [Romain](Romain/21-six-sur-dix.png)*

### La récompense du village

Une épreuve réussie attribue le bonus annoncé. L'**Indice** nomme trois vivants dont au moins un loup. La **Seconde vision** donne deux inspections de plus à la Voyante. La **Protection** rend un membre du village présent à la clôture insensible aux loups la nuit suivante, et lui seul le sait.

*Cartes de : [Thomas](Thomas/21-la-recompense-du-village.png)*


## Légendes du village

### La retraite du coq

Le vieux coq a cédé sa place à son neveu. Il continue de se lever avant lui, uniquement pour vérifier qu'il dort bien.

*Cartes de : [Romain](Romain/09-la-retraite-du-coq.png)*

### Le fromage de la lune

À la fromagerie, on jure que la lune a des trous des deux côtés. La discussion reprend chaque fois que quelqu'un se propose de la retourner.

*Cartes de : [Romain](Romain/17-le-fromage-de-la-lune.png)*

### La soupe du mardi

La cuisinière assure que ses navets sentent venir la pleine lune. Le potager, consulté pour un second avis, a préféré garder le silence.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-02-34.png)*

### La chaise du menuisier

Le menuisier a signé sa plus belle chaise sous le siège. À l'exposition, il a passé la journée à quatre pattes pour recevoir les compliments.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-25.png), [Line](Line/10-la-chaise-du-menuisier.png)*

### Le tailleur de brume

Le tailleur a coupé dans le brouillard une superbe cape à sa taille. Il l'a laissée sécher dans la cour et la cherche depuis.

*Cartes de : [Thomas](Thomas/09-le-tailleur-de-brume.png)*

### Le portrait du vent

Une peintre est venue faire le portrait du vent. Elle est repartie avec trois feuilles blanches et un chapeau de moins.

*Cartes de : [Thomas](Thomas/17-le-portrait-du-vent.png)*


## Fin de manche et prix de la soirée

### Le dernier vivant

Au dépouillement ou à l'aube après les sauvetages, le seul camp qui a encore un habitant engagé en vie gagne. Aucun survivant ? La manche se termine sans vainqueur. S'il reste un loup et un membre du village, la partie continue.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-03-57.png), [Line](Line/16-le-dernier-vivant.png)*

### Les points du conseil

En manche comptée, un membre du village marque 1 point par vote contre un loup au conseil. Un défi humain déclaré réussi rapporte 1 point à chaque équipe humaine engagée à son ouverture, même silencieuse ou éliminée. L'élection du Capitaine vaut zéro point.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-04-03.png)*

### Rester jusqu'au bout

À la clôture d'une épreuve IA en manche comptée, un membre du village présent marque 1 point si le groupe réussit. Un loup présent marque 2 points si le groupe échoue. Être là à la clôture compte, même après avoir donné sa réponse.

*Cartes de : [Line](Line/17-rester-jusqu-au-bout.png), Romain*

### Après la cloche

Une équipe arrivée en retard peut encore s'engager. Elle reçoit le rôle de simple villageois ou de loup et marque sur les votes et les épreuves à venir. Pour gagner les points de victoire de camp, son habitant doit avoir été engagé dès la cloche.

*Cartes de : [Romain](Romain/22-apres-la-cloche.png)*

### Champion du village

En manche comptée, si ton camp gagne et que tu étais engagé à la cloche, une victoire en vie rapporte 5 points, une victoire après ta mort en rapporte 3. Le prix Champion additionne les manches comptées closes. Les essais et les manches annulées sont écartés.

*Cartes de : [Thomas](Thomas/22-champion-du-village.png)*

### Le prix de Sobriété

La Sobriété récompense le plus faible coût par point. On compte les appels lancés pendant vos engagements en manches comptées closes. Il faut des points et au moins la moitié du meilleur total Champion. Si seul le Champion franchit ce seuil, la moindre dépense des autres équipes ayant…

*Cartes de : [Thomas](Thomas/23-le-prix-de-sobriete.png)* - *texte coupé sur la capture (la suite n'était pas visible)*

### Trois prix, trois équipes

Les prix sont attribués dans l'ordre Champion du village, Sobriété, puis Jury. À chaque étape, la meilleure équipe encore disponible reçoit le prix : une équipe ne repart qu'avec un seul prix. Sans note du jury, une équipe ne concourt pas au prix Jury.

*Cartes de : [Thomas](Thomas/24-trois-prix-trois-equipes.png), [Line](Line/18-trois-prix-trois-equipes.png)*

### La minute du jury

Tu as 60 secondes pour présenter l'agent, le framework et les outils de ton équipe. Montre une décision concrète prise en jeu et le choix technique qui l'a rendue possible. Les trois jurés s'accordent ensuite sur une note commune sur 20.

*Cartes de : [Clément](Cl%C3%A9ment/Capture%20d%E2%80%99%C3%A9cran%20du%202026-11-26%2019-04-10.png)*

### Loin du sentier battu

Le starter kit n'est qu'un point de départ. Plus votre agent s'éloigne, mieux le jury perçoit votre travail à la soutenance : architecture, mémoire, outils, prompts, stratégie. Gardez la trace de ce que vous avez changé, et sachez dire pourquoi.

*Cartes de : [Romain](Romain/24-loin-du-sentier-battu.png)*


## Aide-mémoire chiffré

Les chiffres des cartes, regroupés pour le code de l'agent.

| Sujet | Valeur | Carte |
|---|---|---|
| Vue de jour | 22 m | Les yeux de la meute |
| Vue de 22 h à 8 h | 8 m (village), 16 m (loup) | Les yeux de la meute |
| Voix : chuchote / parle / crie | 4 / 12 / 26 m (environ moitié derrière un obstacle) | Porter la voix |
| Parole | 240 caractères max, environ 2 s entre deux paroles | Porter la voix |
| Pas : furtif / marche / course | 2 / 6 / 13 m (environ moitié derrière un mur) | Les bottes dans la boue |
| Voix identifiée | moins de 6 m, sans mur, ou silhouette visible | Une voix dans ton dos |
| Distance pour `sit` | 2 m d'un banc (2 places conseil et chapelle, 4 cantine) | Le banc du conseil |
| `return_home` | transport après 10 s, 1 demande par minute, `move` l'annule | Le chemin du retour |
| Sommeil | moins de 7 h dans un lit (22 h-8 h) : fatigue, `self.fatigue` | Sept heures de sommeil |
| Journal du village | 240 caractères, 1 publication par 60 s | Le journal du village |
| Cycle jour/nuit | 10 min réelles, soit 25 s par heure | Le premier matin |
| Premier jour | cloche à 8 h, élection du Capitaine 9 h-11 h | Le premier matin |
| Conseil | convoqué vers 17 h, vote de 19 h à 21 h | Le bulletin du soir |
| Épreuve | annonce à 14 h, ouverture à 15 h | La place à quatorze heures |
| Notes `memo` | chaque matin à 8 h, consigne corrigée vers 10 h 30 | Les notes du matin |
| Chasse des loups | `transform` à 2 m de la pierre, de 22 h à 6 h | La pierre de la meute |
| Voyante | 2 inspections par manche, 1 par nuit, depuis sa maison | L'œil de la Voyante |
| Sorcière | 1 potion de vie et 1 de mort par manche, 1 par nuit, avant 8 h | Les deux fioles |
| Succession du Capitaine | 10 s avec `name_successor` | L'insigne du Capitaine |
| Réussite d'une épreuve IA | 60 % (arrondi au supérieur), 40 % pour la recherche du jour | Six sur dix, La recherche du jour |
| Points (manche comptée) | village : 1 par vote contre un loup, 1 par épreuve IA réussie présent | Les points du conseil, Rester jusqu'au bout |
| Points (loup) | 2 si l'épreuve IA échoue, loup présent à la clôture | Rester jusqu'au bout |
| Champion | victoire en vie 5 pts, après la mort 3 pts | Champion du village |
| Quiz humain | 10 s, première réponse validée engage l'équipe | Le quiz à plusieurs voix |
| Jury | 60 s de présentation, note commune sur 20 | La minute du jury |
| Erreurs à connaître | HTTP 409 (2e connexion), 402 (solde épuisé), 1013 (lecteur trop lent) | Un seul établi, La bourse commune, Garder l'oreille ouverte |
