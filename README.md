# Hippique AI — agent multitâche

Le projet inclut maintenant `MultiTaskAgent`, une couche d’orchestration inspirée du principe d’Agent Reach : une demande est décomposée, les agents spécialisés sont sélectionnés en parallèle et l’état des sources est retourné explicitement.

## API

- `GET /api/health` — état du service
- `GET /api/agents` — catalogue des agents
- `GET /api/capabilities` — diagnostic des capacités et sources
- `GET /api/analysis?horse=...` — analyse de démonstration
- `POST /api/chat` — assistant conversationnel
- `POST /api/multitask` — orchestration multitâche

Exemple :

```bash
curl -X POST http://localhost:8000/api/multitask \
  -H 'Content-Type: application/json' \
  -d '{"task":"Analyse Asteria du Clos avec la piste, le jockey et le calendrier"}'
```

Les connecteurs web, RSS, météo et sources officielles sont représentés par un registre de capacités. Ils doivent être branchés à des API autorisées et à leurs clés avant toute collecte réelle. Les résultats actuels utilisent des données de démonstration et ne constituent pas un conseil de pari.
