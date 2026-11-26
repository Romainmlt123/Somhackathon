# Règles

Règles de l'équipe pour l'agent du village.

## Règle 1 : un villageois par tablée

- Votre équipe partage un seul habitant.
- Dans « Mon villageois », vous choisissez son nom, son personnage, sa couleur de peau et jusqu'à 5 accessoires.
- Tout se fige dès que l'habitant est engagé dans une manche.
- Les autres agents voient ses accessoires, jamais sa peau.

## Règle 2 : l'établi Python

- Prenez Python 3.11 ou plus récent.
- Dans le dossier extrait, lancez un venv.

## Règle 3 : garder l'œil ouvert

- Le client écoute le WebSocket pendant que votre stratégie décide.
- Confiez tout calcul bloquant à `await asyncio.to_thread(...)`.
- Si votre agent lit trop lentement, le serveur réunit ses messages `vision` en attente, puis ferme la connexion avec le code 1013.
- Le `snapshot` de la reconnexion remet l'agent à jour.
