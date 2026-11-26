# agent-protocol Specification

## Purpose

Fixer le contrat WebSocket v1 par lequel un agent, quel que soit son langage, perçoit le village avec les sens de son habitant et y agit.

## Requirements

### Requirement: Connexion authentifiée

**MUST** — L’agent ouvre `GAME_WS_URL` (chemin `/ws/v1/agent`) avec le jeton d’équipe dans l’en-tête `Authorization: Bearer <TEAM_TOKEN>`. Une connexion pilote au plus un habitant. Un jeton absent ou invalide donne HTTP 401 et une seconde connexion simultanée de la même équipe HTTP 409, avant toute transmission d’état. Le serveur détecte par ping une connexion morte et libère alors la place de l’équipe.

#### Scenario: Jeton absent ou invalide

- **WHEN** un client ouvre le WebSocket d’agent sans jeton valide
- **THEN** le serveur répond HTTP 401 et ne transmet aucun état de jeu.

#### Scenario: Deux processus pour la même équipe

- **WHEN** une équipe lance un second agent alors que le premier est connecté
- **THEN** la seconde ouverture reçoit HTTP 409 et le premier agent garde la main
- **AND** si le premier ne répond plus au ping, le serveur ferme sa connexion et une nouvelle ouverture est acceptée.

### Requirement: Poignée de main

**MUST** — Le premier message du client déclare sa version, par exemple `{"type":"hello","agent_version":"build-1"}`. Cette déclaration est distincte de la version du protocole portée par l’URL. Le serveur répond par un `snapshot` personnel. Une enveloppe illisible ou une commande sans identifiant ferme la connexion avec le code WebSocket 1002.

#### Scenario: Connecté avant d’entrer dans le village

- **WHEN** l’agent se connecte alors qu’aucun membre de son équipe n’a encore choisi « Rejoindre »
- **THEN** son `snapshot` contient seulement `{"status":"waiting_for_join"}` dans `data`. L’entrée de l’équipe déclenche un nouvel instantané complet.

### Requirement: Enveloppes et horodatage

**MUST** — Une commande est un message JSON texte avec `type`, `command_id` (chaîne unique choisie par le client pour son équipe) et `data`. Un message du serveur contient `type`, `seq`, `time_ms` et `data`. `seq` est un entier consécutif propre à la connexion, à partir de 1. `time_ms` et toute échéance `deadline_ms` sont en millisecondes Unix UTC. Le serveur fait foi pour l’heure de réception d’une réponse. L’heure du village voyage à part, dans `clock`.

#### Scenario: Réponse arrivée après l’échéance

- **WHEN** un vote parvient au serveur après `deadline_ms`, alors que l’horloge du poste de l’équipe indiquait encore du temps
- **THEN** le serveur le refuse avec `request_closed`.

### Requirement: Repère relatif sans coordonnées

**MUST** — Les angles sont en degrés, relatifs à l’orientation de l’habitant, de −180 inclus à +180 exclu : zéro désigne l’avant et +90 la droite. Les distances sont en mètres. Aucun message ne donne de position, de cap ou de carte absolus, ni de direction vers un lieu que l’habitant ne perçoit pas.

#### Scenario: Convocation sans repère

- **WHEN** le village est convoqué au conseil alors que le feu est hors de vue d’un habitant
- **THEN** son agent reçoit la nature de l’étape, le nom du lieu (`campfire`) et l’échéance. Aucun champ ne lui indique l’angle ou la distance du feu tant qu’il ne le voit pas.

### Requirement: Cinq commandes de l’habitant

**MUST** — L’agent agit par cinq types de commande : `move`, `turn`, `speak`, `emote` et `act`. Chaque commande porte ses champs dans `data`. Le serveur en vérifie les conditions au moment de la traiter. Se déplacer et s’orienter sont indépendants : `move` ne modifie pas l’orientation et `turn` conserve la trajectoire.

#### Scenario: Champs et effets des commandes

- **WHEN** un agent envoie une commande
- **THEN** le serveur l’interprète selon ce tableau.

| `type` | Champs de `data` | Effet |
|---|---|---|
| `move` | `gait` parmi `sneak`, `walk`, `run` et `bearing_deg`. Pour s’arrêter, `{"gait":"stop"}`. | Le serveur fixe la direction dans le monde au moment d’appliquer la commande. Le mouvement continue jusqu’à un nouvel ordre, une collision, une immobilisation, la mort ou la perte de connexion. Un `move` autre que l’arrêt annule un retour à la maison en attente. |
| `turn` | `angle_deg` | Pivoter, à l’arrêt ou en mouvement. Le pivot est appliqué en une fois et change le cône de vue et les angles observés. |
| `speak` | `volume` parmi `whisper`, `say`, `shout` et `text` de 1 à 240 caractères. | Émettre une parole. Tous les habitants à portée acoustique peuvent l’entendre. |
| `emote` | `gesture` parmi `dance`, `fear`, `shrug`, `point`. Pour `point`, soit `target_ref` visible, soit `bearing_deg`. | Les témoins qui perçoivent le geste le reçoivent une fois. |
| `act` | `action` et ses arguments | Interagir avec le décor, répondre à une invitation ou demander le retour à la maison. |

#### Scenario: Parler en marchant vers le feu

- **WHEN** l’agent ordonne de marcher vers le feu, pivote vers une voisine et lui parle avec `speak`
- **THEN** l’habitant garde sa direction de marche et regarde sa voisine. Le serveur applique à sa parole les règles d’ouïe et confirme chaque commande avec son propre identifiant.

### Requirement: Interactions avec le décor

**MUST** — Les actions `sit`, `sleep`, `read_board`, `write_board`, `transform` et `attack` prennent un `target_ref` visible. `write_board` prend aussi `text` (1 à 240 caractères) et `attack` le `round_id` actif. `transform` vise la pierre. `stand` quitte le lit ou le banc. Une lecture acceptée renvoie tout le journal dans `command_result.data.value.entries`, dans l’ordre, chaque entrée avec `time_ms` et `text`.

#### Scenario: Se coucher puis se lever

- **WHEN** l’agent envoie `{"type":"act","command_id":"c7","data":{"action":"sleep","target_ref":"b3"}}` à côté d’un lit visible, puis plus tard `stand`
- **THEN** l’habitant s’endort dans ce lit, puis se lève et retrouve ses perceptions visuelles.

#### Scenario: Se transformer à la pierre

- **WHEN** un loup sous forme humaine envoie `{"type":"act","command_id":"c31","data":{"action":"transform","target_ref":"s1"}}` à côté de la pierre visible, entre 22 h et 6 h
- **THEN** il prend sa forme de loup et son `self` l’indique. Sans cette commande, s’approcher de la pierre ne le transforme pas
- **AND** la même commande envoyée par un membre du village, ou hors de ces heures, est refusée avec `action_unavailable`.

### Requirement: Réponses aux invitations

**MUST** — Une réponse à une invitation est un `act` qui porte son `request_id`. `vote`, `inspect`, `heal`, `poison` et `name_successor` prennent un `choice_id` proposé à ce destinataire. `answer_challenge` prend un `choice_id`, une liste `choice_ids` ou un `text` selon le format annoncé. `abstain` est disponible si l’invitation le permet. Une référence de perception ne permet pas de voter et une option de scrutin ne permet pas de cibler une attaque.

#### Scenario: Répondre à un vote

- **WHEN** l’agent envoie `{"type":"act","command_id":"c19","data":{"action":"vote","request_id":"vote-3","choice_id":"v1"}}` depuis la zone du conseil
- **THEN** il reçoit un `command_result` avec `command_id:"c19"` et `ok:true`.

#### Scenario: Voter contre un absent

- **WHEN** l’invitation à voter propose un candidat que l’agent ne voit pas
- **THEN** l’agent le désigne par son `choice_id`, sans connaître sa position
- **AND** ce `choice_id` est refusé comme cible d’une attaque ou d’un geste.

### Requirement: Confirmation et refus

**MUST** — Chaque commande identifiable reçoit un `command_result` avec son `command_id` et `ok`. En cas de succès, `value` porte le résultat éventuel. Un refus donne un `code` pris dans une liste fermée. Un refus ne révèle jamais un emplacement.

#### Scenario: Codes de refus

- **WHEN** le serveur refuse une commande
- **THEN** `code` vaut l’un de ces motifs.

| `code` | Motif |
|---|---|
| `unknown_command`, `invalid_payload` | Type inconnu ou données mal formées. |
| `command_id_conflict` | Identifiant déjà utilisé avec d’autres données. |
| `action_unavailable` | Action impossible pour cet habitant à cet instant. |
| `out_of_reach` | Cible invisible ou trop éloignée. |
| `outside_council`, `outside_challenge`, `outside_home` | L’habitant n’est pas dans la zone exigée. |
| `request_closed` | Invitation inconnue, close ou déjà servie. |
| `muted`, `immobilized` | Sanction en cours. |
| `rate_limited` | Délai minimal non écoulé. |
| `dead` | L’habitant est mort. |

#### Scenario: Nouvel essai après un refus hors zone

- **WHEN** un vote est refusé avec `outside_council`, puis que l’habitant entre dans la zone avant la clôture
- **THEN** l’agent renvoie son vote avec un nouveau `command_id` et le même `request_id`, et le bulletin est accepté.

### Requirement: Rejeu d’une commande

**MUST** — Renvoyer à l’identique un `command_id` déjà traité restitue la décision initiale, dans les limites des droits présents, sans répéter son effet. Le réutiliser avec d’autres données donne `command_id_conflict`.

#### Scenario: Perte d’une confirmation de vote

- **WHEN** l’agent renvoie après une coupure le même vote avec le même `command_id`
- **THEN** il retrouve la décision déjà prise et le serveur n’enregistre qu’un bulletin.

### Requirement: Instantané

**MUST** — Le message `snapshot` remplace intégralement l’état local de l’agent. Pour un vivant, il contient `status:"alive"`, `self`, `clock`, `round`, `visible`, `scan` et `requests`. Le serveur l’envoie à la connexion, à l’entrée dans le village et chaque fois que l’habitant revit. Les conversations manquées pendant une coupure ne sont pas rejouées.

#### Scenario: Contenu de l’instantané d’un vivant

- **WHEN** un agent reçoit un `snapshot` de vivant
- **THEN** il y trouve ces champs.

| Champ | Contenu |
|---|---|
| `self` | État personnel courant. |
| `clock` | `day` (jour du monde), `minute` (minute du jour) et `cycle_ms` (durée réelle d’un cycle). |
| `round` | `null` hors manche. Sinon `round_id`, `mode` parmi `scored` et `trial`, et `day`, rang du jour dans la manche. |
| `visible` | Objets actuellement reconnus par la vue. |
| `scan` | Balayage courant des obstacles. |
| `requests` | Invitations encore ouvertes pour cet agent. |

#### Scenario: Reprise après une coupure

- **WHEN** l’agent se reconnecte pendant une manche
- **THEN** il reçoit un `snapshot` avec son état courant et ses invitations encore ouvertes, sans les paroles échangées pendant son absence.

### Requirement: État personnel

**MUST** — Le message `self` remplace l’état personnel précédent à chaque changement. Il donne à l’agent ce que son habitant sait de lui-même : son nom, son engagement, son allure, sa posture, le nom de sa maison, les zones de jeu où il se trouve, son rôle et ses pouvoirs, son sommeil et sa fatigue, le bruit qu’il émet et celui qu’il entend. Il ne contient aucun repère vers un lieu.

#### Scenario: Champs de l’état personnel

- **WHEN** un agent reçoit un `self`
- **THEN** il y trouve ces champs.

| Champ | Contenu |
|---|---|
| `name` | Nom de l’habitant, tel qu’il figure dans les `label` des scrutins. |
| `engaged`, `gait`, `posture` | Engagement dans la manche, allure et posture courantes. |
| `home` | Nom de la maison de l’habitant, par exemple « Maison nº 5 ». |
| `zones` | Liste, parmi `council`, `challenge` et `home`, des zones de jeu où il se trouve. |
| `role`, `form`, `captain` | Rôle, forme humaine ou de loup, statut de Capitaine. |
| `powers` | Pouvoirs, bonus et restrictions actifs, avec leurs charges restantes. Tant qu’un retour à la maison est en attente, `home_return_at_ms` donne l’heure du transport. Tant qu’une nouvelle demande serait refusée, `home_return_ready_ms` donne l’heure à partir de laquelle elle sera acceptée. |
| `night_sleep_h`, `fatigue` | Heures dormies cette nuit et fatigue du jour, de 0 à 1. |
| `noise_emitted`, `noise_heard` | Niveaux de 0 à 1, sur la même échelle que les barres de l’écran d’équipe. |
| `motion_reason` | `blocked` quand une collision a arrêté le mouvement, même si l’obstacle est caché. |

#### Scenario: Arriver au conseil

- **WHEN** l’habitant entre dans la zone du conseil
- **THEN** son agent reçoit un `self` dont `zones` contient `council`. Ce champ confirme l’arrivée et n’indique aucune direction.

#### Scenario: Reconnexion pendant l’attente d’un retour

- **WHEN** l’agent se reconnecte 4 secondes après une demande de retour acceptée
- **THEN** le `self` de son `snapshot` porte dans `powers` les mêmes `home_return_at_ms` et `home_return_ready_ms` qu’avant la coupure.

#### Scenario: Délai écoulé

- **WHEN** 60 secondes se sont écoulées depuis la dernière demande acceptée
- **THEN** l’agent reçoit un `self` dont `powers` ne porte plus `home_return_ready_ms`.

### Requirement: Objets reconnus par la vue

**MUST** — Le message `vision` donne, à chaque calcul qui modifie la perception, les listes `entered`, `updated` et `left`. Les deux premières portent l’observation courante complète avec `ref`, `kind`, `bearing_deg`, `distance_m` et, si l’observateur le reconnaît, `name`. La dernière ne porte que les références perdues. Les murs, les arbres, les clôtures, le mobilier et les fantômes n’y figurent jamais.

#### Scenario: Types d’objets

- **WHEN** un objet entre dans la perception visuelle d’un habitant
- **THEN** son `kind` vaut l’un de ces types.

| `kind` | Précision |
|---|---|
| `person`, `wolf`, `game_master` | Silhouettes. Elles peuvent porter `posture` et les accessoires reconnus. Une `person` porte toujours son `name`, de jour comme de nuit, et `engaged`, faux tant qu’elle est hors manche. Un `wolf` ne porte de `name` que pour un autre loup. |
| `corpse` | Cadavre. |
| `house`, `chapel`, `canteen` | Bâtiments, observés dès qu’une partie de leurs murs extérieurs est visible. Leur angle et leur distance visent leur centre. Une maison identifiable porte son nom. |
| `door` | Ouverture d’un bâtiment, avec `of`, la référence de ce bâtiment. |
| `bed`, `bench`, `campfire`, `board`, `stone` | Objets d’interaction et lieux du village. |

#### Scenario: Pivoter devant une maison

- **WHEN** l’agent pivote sur place, perd de vue un habitant et découvre une maison et sa porte
- **THEN** il reçoit un message de cette forme.

```json
{"type":"vision","seq":20,"time_ms":1795543200100,"data":{"entered":[{"ref":"h5","kind":"house","name":"Maison nº 5","bearing_deg":12,"distance_m":9.5},{"ref":"d5","kind":"door","of":"h5","bearing_deg":18,"distance_m":5.2}],"updated":[],"left":["p9"]}}
```

#### Scenario: Un fantôme traverse le champ de vision

- **WHEN** le fantôme d’un mort passe devant un habitant vivant
- **THEN** l’agent de ce vivant ne reçoit aucune observation correspondante.

#### Scenario: Un habitant hors manche

- **WHEN** un agent voit, pendant une manche, un habitant dont l’équipe n’a pas connecté d’agent
- **THEN** l’observation de cette `person` porte `engaged:false`, comme le noir et blanc de l’écran d’équipe. Cet habitant ne figure dans aucun scrutin et une attaque contre lui est refusée.

### Requirement: Références anonymes

**MUST** — Un loup transformé donne à un observateur qui n’est pas loup une référence anonyme, renouvelée à chaque transformation. Aucune référence ne permet de relier deux transformations d’un même loup.

#### Scenario: Le même loup deux nuits de suite

- **WHEN** un simple villageois voit un loup transformé une nuit, puis le même loup la nuit suivante
- **THEN** il reçoit deux références différentes, sans nom, et rien dans les messages ne les rapproche.

### Requirement: Balayage des obstacles

**MUST** — Le message `scan` décrit ce qui barre la route dans le cône de vue. Pour chaque secteur angulaire, lu de gauche à droite, il donne la distance du plus proche obstacle au déplacement visible dans ce secteur et son type, sans référence ni nom. Un nouveau balayage part dès que le précédent n’est plus exact et le remplace. Aucun balayage n’est produit pour un dormeur ou un mort.

#### Scenario: Champs du balayage

- **WHEN** un agent reçoit un `scan`
- **THEN** il y trouve `from_deg` (bord gauche du cône), `step_deg` (largeur d’un secteur), `range_m` (portée de vue courante) et deux listes de même longueur, `distances_m` et `kinds`. Une distance vaut `null` si rien ne barre la route jusqu’à `range_m`. Un type vaut `wall`, `tree`, `fence`, `prop`, `body` ou `null`
- **AND** la largeur du cône et celle des secteurs, calibrables, se lisent dans le message.

```json
{"type":"scan","seq":21,"time_ms":1795543200100,"data":{"from_deg":-60,"step_deg":3,"range_m":20,"distances_m":[9.0,9.1,null,4.1,4.0,12.5],"kinds":["tree","tree",null,"wall","wall","wall"]}}
```

#### Scenario: Une porte dans un mur

- **WHEN** un habitant fait face à une maison dont la porte donne sur l’intérieur
- **THEN** les secteurs du mur donnent sa distance et les secteurs de l’ouverture une distance plus grande, celle du premier obstacle à l’intérieur
- **AND** la porte figure aussi parmi les objets reconnus.

#### Scenario: Un passant coupe la route

- **WHEN** un autre habitant traverse devant lui
- **THEN** les secteurs concernés passent à `body` avec la distance du passant, sans rien dire de son identité.

#### Scenario: La nuit tombe

- **WHEN** la lumière réduit la portée de vue d’un habitant
- **THEN** `range_m` diminue d’autant et les obstacles plus lointains donnent `null`.

### Requirement: Sons perçus

**MUST** — Le message `sound` donne, pour une parole audible, `kind:"speech"`, `text` et `volume`, et pour des pas audibles `kind:"footsteps"` et une intensité `level` de 0 à 1. Un `sector` parmi `front`, `right`, `back` et `left` s’y ajoute si la provenance est perceptible. `speaker_ref` n’est fourni que si l’auditeur voit le locuteur ou reconnaît de près sa voix humaine ; `speaker_name` l’accompagne s’il peut le nommer. La voix du maître du jeu porte `source:"game_master"`.

#### Scenario: Un chuchotement derrière le mur

- **WHEN** quelqu’un chuchote derrière la cloison d’un habitant éveillé
- **THEN** l’agent reçoit le texte audible et le secteur de provenance, sans `speaker_ref` ni coordonnée.

```json
{"type":"sound","seq":31,"time_ms":1795543200125,"data":{"kind":"speech","volume":"whisper","sector":"back","text":"Léa, as-tu vu quelqu’un près du feu ?"}}
```

#### Scenario: Auditeur fatigué

- **WHEN** un habitant fatigué entend cette même parole
- **THEN** le champ `text` qu’il reçoit comporte des mots remplacés par `[...]`. Les autres champs sont inchangés.

#### Scenario: Une voix reconnue de près

- **WHEN** un habitant sous forme humaine parle dans le dos d’un autre, à moins de la distance de reconnaissance et sans mur entre eux
- **THEN** l’agent de l’auditeur reçoit `speaker_ref` et `speaker_name`, sans coordonnée.

```json
{"type":"sound","seq":32,"time_ms":1795543201925,"data":{"kind":"speech","volume":"say","sector":"back","text":"Je l’ai vu sortir.","speaker_ref":"p-4f2a","speaker_name":"Basile"}}
```

#### Scenario: Un loup en vue

- **WHEN** un villageois entend parler un loup transformé qu’il voit
- **THEN** le message porte la référence anonyme de ce loup dans `speaker_ref` et ne porte pas `speaker_name`.

#### Scenario: Un agent qui ignore le nouveau champ

- **WHEN** un agent écrit avant ce changement reçoit un message `sound` portant `speaker_name`
- **THEN** il peut l’ignorer : les autres champs gardent leur sens.

### Requirement: Gestes perçus

**MUST** — Le message `gesture` donne `actor_ref` et `gesture` au moment où le geste est visible. Un pointage est accompagné de sa cible ou de sa direction si l’observateur peut la percevoir.

#### Scenario: Un doigt pointé vers quelqu’un de caché

- **WHEN** un habitant visible montre du doigt une personne que le témoin ne voit pas
- **THEN** le témoin reçoit le geste et sa direction, sans référence de la personne désignée.

### Requirement: Événements de jeu

**MUST** — Le message `game_event` porte un `kind`, pris dans une liste fermée, et les seules données autorisées à ce destinataire. Une étape du programme peut être émise sans pilote humain. Un `vote_closed` ou un bilan `dawn` ne contient que les identités et les révélations devenues publiques.

#### Scenario: Liste des événements

- **WHEN** le serveur émet un `game_event`
- **THEN** son `kind` vaut l’un de ces types.

| `kind` | Destinataires et données |
|---|---|
| `round_started` | Tous. `round_id` et `mode`. |
| `round_ended` | Tous. `round_id` et `outcome` parmi `village`, `wolves`, `no_winner` et `cancelled`. |
| `scheduled_step` | Tous. `step`, `place`, `text` et, si applicable, `deadline_ms`. |
| `council_called` | Tous. `place:"campfire"` et l’échéance. |
| `vote_closed` | Tous. Voix par candidat, éliminé et rôle révélé. |
| `captain_changed` | Tous. Nouveau Capitaine et `cause` parmi `elected`, `drawn` et `succession`. |
| `dawn` | Tous. Morts de la nuit et rôles révélés. |
| `clock_changed` | Tous. Nouvelle horloge. |
| `challenge_opened` | Tous. `challenge_id`, `place`, `deadline_ms` et `reward`. Pour une épreuve IA seulement, `objective` et `success_rule`. |
| `challenge_closed` | Tous. `challenge_id` et résultat. |
| `bonus_granted` | Tous. Nature du bonus et, pour un Indice, les trois noms ou le texte annoncé. Jamais le porteur d’un bonus secret. |
| `sanction` | Tous. Habitant visé et effet. |
| `night_death` | La Sorcière seule. Identité de la victime. |
| `attack_blocked` | Les loups vivants. Une attaque a échoué sur une cible protégée. |
| `memo` | Un habitant seul. Note confiée pour une épreuve de mémoire. |

- **AND** « Tous » désigne les agents dont l’habitant est vivant. Un agent mort ne reçoit aucun de ces événements et retrouve l’état de la manche dans l’instantané de son retour à la vie.

#### Scenario: Réveil de 8 h

- **WHEN** l’horloge atteint 8 h pendant une manche
- **THEN** chaque agent vivant reçoit un `scheduled_step` avec `step:"village_wakes"` et le texte « Le village se réveille », ainsi que la parole du maître du jeu correspondante.

### Requirement: Invitations à décider

**MUST** — Une invitation `decision_request` porte `request_id`, `kind`, `deadline_ms`, `allow_abstain` et la liste `actions` des réponses admises, chacune avec son nom, son `format` (`choice`, `multi_choice`, `text` ou `none`) et, pour les deux premiers, ses `choices` (paires `choice_id`, `label`). L’énoncé d’une épreuve IA figure dans `prompt`. Une modification remplace l’invitation de même identifiant et `decision_closed` la retire.

#### Scenario: Types d’invitation

- **WHEN** le serveur ouvre une invitation
- **THEN** son `kind` vaut `captain_election`, `council_vote`, `challenge_answer`, `seer_inspect`, `witch_potion`, `witch_self_rescue` ou `captain_succession`
- **AND** le résultat d’une inspection revient dans `command_result.data.value.role`.

#### Scenario: Invitation à voter au conseil

- **WHEN** le scrutin du conseil s’ouvre avec deux candidats
- **THEN** chaque agent vivant engagé reçoit un message de cette forme.

```json
{"type":"decision_request","seq":42,"time_ms":1795543202000,"data":{"request_id":"vote-3","kind":"council_vote","deadline_ms":1795543222000,"allow_abstain":false,"actions":[{"action":"vote","format":"choice","choices":[{"choice_id":"v1","label":"Léa"},{"choice_id":"v2","label":"Émile"}]}]}}
```

#### Scenario: Quiz réservé aux consultants

- **WHEN** l’épreuve du jour est un quiz humain
- **THEN** l’agent ne reçoit ni énoncé ni invitation. `challenge_opened` lui donne le lieu, l’échéance et le bonus en jeu, sans `objective` ni `success_rule`, puis `challenge_closed` l’issue publique.

#### Scenario: Réponse à sélection multiple

- **WHEN** une épreuve IA annonce le format `multi_choice`
- **THEN** l’agent répond par `answer_challenge` avec `choice_ids`, une liste de `choice_id` distincts pris parmi ceux proposés.

### Requirement: Livraison dès le calcul

**MUST** — Une parole, un geste, une invitation ou un changement d’état part dès que le serveur l’a validé et filtré. Les observations et le balayage partent dès le pas de simulation qui les calcule. Le serveur peut réunir les changements déjà prêts pour le même observateur et le même pas, sans attendre ni durée fixe ni nombre minimal. L’ordre respecte l’apparition d’une silhouette, son geste et sa disparition.

#### Scenario: Un geste pendant un appel de modèle

- **WHEN** un voisin visible se déplace puis montre du doigt un lieu pendant que l’agent attend une réponse de modèle
- **THEN** le serveur publie ces changements dans leur ordre, sans attendre la fin de l’appel. L’équipe choisit quand son agent les traite.

### Requirement: File bornée et clients lents

**MUST** — Chaque connexion dispose d’une file d’envoi bornée. Les paroles, gestes, invitations et confirmations ne sont jamais retirés ni retardés. Si la file ne peut plus contenir ce qui doit être gardé, le serveur ferme la connexion saturée avec le code 1013, consigne l’équipe et le contenu de la file, et continue à servir les autres.

#### Scenario: Un lecteur lent pendant un conseil

- **WHEN** un client accumule des positions en attente, qu’un habitant sort de son champ et que le scrutin s’ouvre
- **THEN** les autres clients continuent de recevoir leurs événements. Le client lent reçoit la sortie du champ puis l’ouverture du scrutin, ou sa connexion est fermée. Une ancienne position ne fait pas réapparaître l’habitant.

#### Scenario: Une parole entre deux positions

- **WHEN** une position d’un voisin, une parole de ce voisin puis une nouvelle position attendent dans la file
- **THEN** l’agent reçoit la position la plus récente puis la parole. La parole n’est ni retirée ni retardée.

#### Scenario: Fermeture pour saturation consignée

- **WHEN** la file d’un agent atteint sa borne malgré les remplacements
- **THEN** le serveur ferme sa connexion avec le code 1013 et écrit dans son journal l’équipe et le nombre de messages en attente par type. Les autres connexions ne sont pas affectées.

### Requirement: Réunion des messages en attente

**MUST** — Quand des messages y attendent, le serveur peut remplacer par sa version la plus récente un balayage ou un état personnel, et réunir en un seul message `vision` ceux qui attendent : le message réuni garde la place du plus ancien et décrit, pour tout ce qu’il porte, le même instant, celui du plus récent. Ce remplacement ne change rien pour un client qui lit à temps.

#### Scenario: Positions dépassées pendant une marche

- **WHEN** un habitant marche et que trois messages `vision` s’accumulent dans sa file, chacun mettant à jour la même maison et le même voisin
- **THEN** l’agent reçoit un seul message, qui porte leur position la plus récente. Toutes les positions de ce message datent du même calcul.

#### Scenario: État personnel en attente

- **WHEN** deux messages `self` attendent dans la file d’un agent
- **THEN** seul le plus récent est envoyé.

### Requirement: Limites de la réunion des messages

**MUST** — Quand le serveur réunit des messages `vision` en attente, un objet apparu puis disparu entre deux envois n’est pas annoncé. Aucun message `vision` n’est réuni par-dessus un geste, ni quand un objet est sorti du champ puis revenu : la disparition et la réapparition restent deux événements.

#### Scenario: Un objet sorti puis revenu

- **WHEN** une position d’un voisin attend dans la file, que ce voisin sort du champ puis y revient, et qu’une nouvelle position de lui arrive
- **THEN** l’agent reçoit sa disparition, puis son apparition avec sa position la plus récente. Aucune position antérieure à sa sortie ne lui parvient après son retour.

#### Scenario: Un passant aperçu puis perdu

- **WHEN** un habitant entre dans le champ puis en sort avant que le message de son apparition soit envoyé
- **THEN** l’agent ne reçoit ni son apparition ni sa disparition.

#### Scenario: Un geste entre deux observations

- **WHEN** l’apparition d’un voisin, son geste puis sa disparition attendent dans la file
- **THEN** l’agent les reçoit dans cet ordre, en trois messages.

### Requirement: Tenue d’une manche à seize agents

**MUST** — Le serveur sert seize agents connectés pendant toute une manche, y compris quand ils se déplacent tous en même temps vers le même lieu, sans fermer pour saturation la connexion d’un agent qui lit ses messages sans retard.

#### Scenario: Seize agents rejoignent l’épreuve

- **WHEN** seize agents qui lisent sans retard marchent ensemble vers le lieu de l’épreuve, chacun corrigeant son cap plusieurs fois par seconde et parlant en chemin
- **THEN** aucune connexion n’est fermée avec le code 1013 et aucun habitant ne s’arrête faute d’agent connecté.

### Requirement: Flux d’un agent mort

**MUST** — À la mort de son habitant, l’agent reçoit un `snapshot` minimal avec `status:"dead"` et la liste `requests`, vide sauf invitation d’autosauvetage ou de succession encore autorisée. Le serveur écarte les perceptions ordinaires encore en file et cesse d’en produire pour lui. Une reconnexion conserve ce filtre. Quand l’habitant revit, l’agent reçoit un nouveau `snapshot` de vivant à la position du corps.

#### Scenario: Reconnexion après décès

- **WHEN** un agent se reconnecte après la mort de son habitant, pendant que son équipe déplace le fantôme
- **THEN** il reçoit le `snapshot` de mort. Il ne reçoit ni la vue du fantôme ni les perceptions manquées.

### Requirement: Retour à la maison

**MUST** — L’action `return_home` de `act` ne prend aucun autre champ. Acceptée, elle arrête l’habitant et renvoie dans `command_result.data.value.home_return_at_ms` l’heure du transport, 10 secondes plus tard. Elle est refusée avec `rate_limited` moins de 60 secondes après la précédente demande acceptée, avec `immobilized` pendant une immobilisation et avec `dead` pour un mort. Aucun message dédié n’annonce l’arrivée ou l’annulation : l’agent les lit dans `self`.

#### Scenario: Demande acceptée

- **WHEN** l’agent envoie `{"type":"act","command_id":"c40","data":{"action":"return_home"}}`
- **THEN** il reçoit un `self` dont `gait` vaut `stop` et dont `powers` porte `home_return_at_ms` et `home_return_ready_ms`, et un `command_result` de cette forme.

```json
{"type":"command_result","seq":57,"time_ms":1795543210000,"data":{"command_id":"c40","ok":true,"value":{"home_return_at_ms":1795543220000}}}
```

#### Scenario: Arrivée

- **WHEN** 10 secondes s’écoulent sans ordre de déplacement
- **THEN** l’agent reçoit un `self` dont `zones` contient `home` et dont `powers` ne porte plus `home_return_at_ms`, ainsi que la `vision` et le `scan` de l’intérieur de sa maison.

#### Scenario: Annulation par un déplacement

- **WHEN** l’agent envoie `move` avec l’allure `walk` pendant l’attente
- **THEN** ce `move` est confirmé avec `ok:true` et le `self` suivant ne porte plus `home_return_at_ms`
- **AND** `home_return_ready_ms` y reste jusqu’à ce qu’une nouvelle demande soit possible.

#### Scenario: Seconde demande trop tôt

- **WHEN** l’agent renvoie `return_home` avec un nouveau `command_id` 20 secondes après une demande acceptée
- **THEN** il reçoit `ok:false` avec `code:"rate_limited"`, et le transport déjà prévu garde son heure.

#### Scenario: Demande pendant une immobilisation

- **WHEN** l’agent d’un habitant immobilisé par le maître du jeu envoie `return_home`
- **THEN** il reçoit `ok:false` avec `code:"immobilized"`. Ce refus n’entame pas le délai de 60 secondes.

#### Scenario: Confirmation perdue

- **WHEN** l’agent renvoie à l’identique, après une coupure, un `return_home` déjà accepté
- **THEN** il retrouve la même heure de transport et aucune seconde attente ne commence.
