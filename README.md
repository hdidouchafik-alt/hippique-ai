# Hippique AI — version 0.4

## Fonctionnalités

- Agents hippiques spécialisés et `MultiTaskAgent`.
- Collecte publique RSS et météo Open-Meteo.
- Cache SQLite avec expiration.
- Catalogue d'hippodromes français avec coordonnées météo.
- API courses, hippodromes, capacités et orchestration.
- Tests automatisés et workflow GitHub Actions.
- Déploiement Render via `render.yaml`.

## Lancer

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Tests :

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Déployer

- **Render** : connecter le dépôt et utiliser `render.yaml`.
- **GitHub Pages** : le frontend actuel dépend de FastAPI et n'est donc pas déployable seul sur Pages. Pour Pages, exporter une version statique du dossier `static/` et du template, puis remplacer les appels API par une URL Render configurée.

Les données de chevaux restent un jeu de démonstration tant qu'un fournisseur officiel autorisé n'est pas configuré. L'application n'invente pas les résultats et ne contourne pas les accès privés. Ce service ne constitue pas un conseil de pari.
