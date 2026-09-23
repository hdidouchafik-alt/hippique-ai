# Hippique AI

Le MultiTaskAgent récupère maintenant des données publiques lorsque possible :

- flux RSS hippiques ;
- météo actuelle via Open-Meteo, sans clé API ;
- lecture contrôlée de pages HTTP(S) via `PublicSourceAgent` ;
- statut et date de collecte pour chaque source ;
- exécution parallèle des collectes et agents spécialisés.

Les sources officielles nécessitant authentification ne sont pas contournées. Les données externes peuvent être indisponibles et doivent être vérifiées avant utilisation. Les résultats ne constituent pas un conseil de pari.

## Lancement

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Mission multitâche

```bash
curl -X POST http://localhost:8000/api/multitask \
  -H 'Content-Type: application/json' \
  -d '{"task":"Analyse les prochaines courses avec la météo","sources":["rss","weather"]}'
```
