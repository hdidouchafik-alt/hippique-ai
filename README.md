# Hippique AI

Une IA dédiée au monde hippique, pensée comme un assistant d’analyse de courses, de chevaux, de jockeys, d’entraîneurs et d’hippodromes.

## Fonctionnalités

- Analyse de chevaux et de performances
- Suivi des performances par piste, distance et conditions
- Profil des jockeys et entraîneurs
- Analyse des prochaines courses et du calendrier
- Recommandations prudentes et structurées
- Assistant conversationnel en français
- Architecture modulaire multi-agents

## Agents spécialisés

- CourseAgent : analyse de la course et de la stratégie
- HorseAgent : forme, pedigree, rythme et potentiel
- JockeyAgent : statistiques et compatibilité
- TrainerAgent : performance de l’écurie et préparation
- TrackAgent : influence de la piste et des conditions
- CalendarAgent : agenda et éventails
- ForecastAgent : synthèse et score global
- AssistantAgent : interface conversationnelle

## Stack

- Python 3.11+
- FastAPI
- Jinja2
- HTML / CSS / JavaScript

## Lancement rapide

1. Créez un environnement virtuel
2. Installez les dépendances
3. Lancez le serveur

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Puis ouvrez :

```text
http://localhost:8000
```

## Structure du projet

```text
main.py
requirements.txt
README.md
templates/
  index.html
static/
  styles.css
  app.js
```

## Exemple de usage

- “Quel cheval est le plus solide sur piste lourde ?”
- “Analyse le profil de Asteria du Clos.”
- “Quel est le meilleur candidat pour la prochaine course ?”
- “Que faut-il surveiller sur l’hippodrome de Chantilly ?”

## Notes

Le projet est conçu comme une base solide pour un assistant hippique intelligent, avec des agents spécialisés et des données simulées faciles à remplacer par des données réelles ou des API externes.
