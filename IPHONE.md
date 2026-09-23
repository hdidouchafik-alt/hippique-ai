# Ouvrir Hippique AI sur iPhone 15

L'application doit d'abord être publiée sur une URL HTTPS. Le dépôt contient déjà `render.yaml` pour un déploiement Render.

## Déploiement recommandé

1. Ouvrir https://dashboard.render.com/
2. Créer un **New Web Service** et sélectionner `hdidouchafik-alt/hippique-ai`.
3. Vérifier :
   - Build command : `pip install -r requirements.txt`
   - Start command : `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Lancer le déploiement.

## Installation sur l'iPhone

1. Ouvrir l'URL Render dans Safari.
2. Appuyer sur **Partager**.
3. Choisir **Sur l'écran d'accueil**.
4. Appuyer sur **Ajouter**.

L'interface est configurée comme une PWA avec un manifeste, une icône et un service worker. Elle peut donc s'ouvrir comme une application depuis l'écran d'accueil. Les appels API nécessitent que l'URL soit celle du même service HTTPS.
