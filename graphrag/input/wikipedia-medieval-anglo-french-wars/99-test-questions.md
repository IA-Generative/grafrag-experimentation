# Test Questions For The Medieval Wars Corpus

## Suggested questions

1. Quelles sont les causes dynastiques et territoriales de la guerre de Cent Ans ?
2. Pourquoi la bataille de Crecy est-elle souvent presentee comme un tournant tactique ?
3. Quel traite suit la bataille de Poitiers de 1356 et que change-t-il pour les territoires francais ?
4. Comment Charles V contribue-t-il au redressement francais apres les grandes defaites initiales ?
5. Compare les objectifs et les consequences du traite de Bretigny et du traite de Troyes.
6. Quel role joue Jeanne d'Arc dans le siege d'Orleans et dans la legitimation du camp francais ?
7. Comment Henri V exploite-t-il la victoire d'Azincourt sur le plan militaire et politique ?
8. Quels documents du corpus montrent que la guerre de Cent Ans n'est pas un conflit continu ?

## Query example

```bash
curl -fsS -X POST http://localhost:8081/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Compare le traite de Bretigny et le traite de Troyes.","method":"global","top_k":6}'
```
