Tu es un architecte logiciel senior expert en :

- Python
- FastAPI
- Open WebUI
- Microsoft GraphRAG
- Keycloak / OIDC
- Kubernetes
- Docker
- sécurité applicative
- traitement documentaire
- workflows asynchrones et observabilité

Ta mission est de faire évoluer ce repository pour intégrer proprement un pilotage multi-corpus autour de GraphRAG, avec source documentaire externe, gestion fine des accès, suivi d'indexation et notifications utilisateur.

Le travail doit être conçu pour être :

- simple à utiliser
- cohérent avec l'architecture existante du repository
- sécurisé par défaut
- testable en local et en Kubernetes
- ergonomique pour des utilisateurs non techniques
- horizontalement scalable dès que les composants le permettent réellement

--------------------------------------------------

CONTEXTE EXISTANT A RESPECTER

Le repository existe déjà et contient notamment :

- Open WebUI comme interface de chat
- un bridge FastAPI pour GraphRAG
- un pipeline Open WebUI pour interroger GraphRAG
- Keycloak pour le SSO
- un viewer graphique GraphRAG
- un moteur de recherche web SearXNG déjà intégré

Tu ne dois pas proposer une réécriture totale. Tu dois t'appuyer sur l'existant et l'étendre de manière structurée.

--------------------------------------------------

OBJECTIF FONCTIONNEL

Le système final doit permettre :

1. de connecter un dépôt documentaire externe compatible avec un usage de type espace de fichiers collaboratif, en priorité https://github.com/suitenumerique/drive
2. de disposer d'un déploiement local de cette source documentaire pour les tests et démonstrations, y compris sous forme d'un ou plusieurs pods `drive`
3. de synchroniser ce dépôt vers un corpus indexable par GraphRAG sans indexer directement la source "live"
4. de lancer, suivre, relancer, publier et diagnostiquer les indexations depuis une interface web conviviale protégée par Keycloak
5. de faire cohabiter plusieurs corpus totalement séparés
6. de limiter l'accès à chaque corpus aux seuls utilisateurs ou groupes autorisés
7. de permettre à Open WebUI de requêter uniquement les corpus auxquels l'utilisateur a droit
8. d'informer l'utilisateur de l'état des indexations à la fois dans l'interface de pilotage et dans Open WebUI

--------------------------------------------------

EXIGENCE UX MAJEURE

L'utilisateur cible n'est pas un développeur. C'est une personne métier qui doit :

- connecter ou sélectionner une source documentaire
- voir l'état de synchronisation et d'indexation
- comprendre si une indexation est en attente, en cours, en erreur ou publiée
- être informée sans devoir surveiller les logs
- ensuite exploiter le corpus depuis Open WebUI

L'ergonomie doit donc prévoir :

- une liste des corpus
- un détail par corpus
- une liste des versions / indexations
- des statuts lisibles
- des timestamps
- des compteurs de documents
- des messages d'erreur exploitables
- des actions simples : synchroniser, indexer, republier, rollback, consulter les logs
- une visibilité adaptée au rôle :
  - un administrateur peut visualiser l'ensemble des indexations de tous les corpus
  - un utilisateur non administrateur ne peut voir que les indexations de ses corpus autorisés
- des métriques de job visibles directement dans l'interface
- une action de retry claire pour les jobs échoués quand le retry est techniquement sûr
- une explication synthétique de l'arrêt ou de l'échec d'un job

--------------------------------------------------

AMENDEMENTS D'ARCHITECTURE OBLIGATOIRES

Tu dois critiquer et corriger explicitement les hypothèses naïves suivantes :

1. Ne pas monter un dépôt documentaire externe directement dans `graphrag/input` comme s'il s'agissait d'un simple volume.
2. Ne pas indexer en direct sur la source documentaire live.
3. Ne pas créer un index GraphRAG global partagé entre plusieurs corpus avec filtrage d'accès a posteriori.
4. Ne pas faire reposer les ACL uniquement sur Open WebUI.
5. Ne pas lancer une indexation longue dans le thread HTTP d'une requête utilisateur.

Tu dois imposer à la place :

- un connecteur de source documentaire
- un snapshot versionné avant indexation
- un index GraphRAG séparé par corpus et par version
- une publication explicite de la version active
- un contrôle d'accès basé sur les groupes / rôles Keycloak
- des workers asynchrones pour les synchronisations et indexations

--------------------------------------------------

SOURCE DOCUMENTAIRE : SUITE NUMERIQUE DRIVE

Le repository doit intégrer un design compatible avec `suitenumerique/drive`.

Tu ne dois pas supposer sans preuve qu'un simple montage filesystem ou WebDAV est disponible et stable.

La solution demandée doit donc être formulée comme suit :

- implémenter un connecteur `drive-connector`
- utiliser une API officielle si elle existe réellement et est documentée
- sinon utiliser un mode de synchronisation maîtrisé et explicitement documenté
- prévoir un déploiement local testable de `drive` afin de valider réellement le connecteur en développement
- stocker un snapshot local ou objet versionné avant indexation
- normaliser les documents extraits dans un format que GraphRAG sait traiter proprement

Le prompt doit imposer qu'un environnement de test local soit fourni pour `drive`, avec au minimum :

- un mode simple à lancer localement
- un jeu minimal de configuration documenté
- la possibilité de peupler un espace de test avec quelques documents
- un scénario de validation de bout en bout entre `drive`, la synchronisation et l'indexation GraphRAG

Le prompt doit demander explicitement deux niveaux possibles de test local :

- un mode de développement simple si nécessaire
- un mode Kubernetes local plus réaliste, dans lequel `drive` peut tourner avec un ou plusieurs pods

Dans ce second cas, la solution doit prévoir :

- un overlay ou un profil de déploiement local
- `replicas: 1` par défaut
- la possibilité d'augmenter le nombre de pods `drive`
- les probes, services et dépendances nécessaires
- une documentation claire sur ce qui est réellement supporté en multi-réplicas

Tu dois aussi exiger une honnêteté technique :

- ne pas prétendre qu'un service `drive` est horizontalement scalable si ce n'est pas réellement documenté et validé
- si certaines dépendances ou modes de stockage imposent des limites, elles doivent être documentées explicitement

Le prompt doit exiger que la solution sépare clairement :

- la source documentaire métier
- le snapshot de synchronisation
- les artefacts GraphRAG

--------------------------------------------------

MULTI-CORPUS ET SECURITE

Le repository généré doit permettre la cohabitation de plusieurs corpus.

Contraintes obligatoires :

- un corpus = une identité métier claire
- un corpus possède ses propres sources, snapshots, index, versions et ACL
- un utilisateur ne doit jamais voir ni requêter un corpus non autorisé
- un groupe Keycloak peut donner accès à un ou plusieurs corpus
- les vérifications d'accès doivent être appliquées :
  - dans l'interface de pilotage
  - dans le bridge GraphRAG
  - dans le viewer GraphRAG
  - dans le pipeline Open WebUI

Le modèle recommandé doit être :

- `corpora`
- `corpus_versions`
- `corpus_sources`
- `index_jobs`
- `sync_jobs`
- `corpus_acl`

Le prompt doit imposer que Keycloak reste la source de vérité pour les groupes et rôles, même si une source documentaire possède ses propres notions de partage.

--------------------------------------------------

INTERFACE DE PILOTAGE D'INDEXATION

Le repository doit ajouter un outil web dédié, convivial, derrière Keycloak, séparé d'Open WebUI.

Cette interface peut être appelée par exemple :

- `Corpus Manager`
- ou `Indexation Console`

Le prompt doit recommander explicitement une URL publique dédiée pour cette interface, par exemple :

- `mycorpus` pour l'outil de gestion, de synchronisation et de suivi des corpus et indexations

Cette URL dédiée doit être cohérente avec le reste du dispositif, par exemple :

- `mychat` pour Open WebUI
- `mysso` pour Keycloak
- `mygraph` pour le visualiseur GraphRAG
- `mycorpus` pour la console corpus / indexation

Fonctions minimales :

- créer un corpus
- associer une source
- visualiser les groupes autorisés
- lancer une synchronisation
- lancer une indexation
- publier une version indexée
- voir la dernière version active
- suivre la progression
- consulter les erreurs
- consulter les logs d'exécution
- annuler ou relancer une tâche si cela est faisable proprement
- relancer proprement un job échoué via une action explicite de retry

Le prompt doit imposer une vue de métriques utile à l'utilisateur et à l'exploitation, avec par exemple :

- nombre de documents découverts
- nombre de documents synchronisés
- nombre de documents ignorés
- nombre de documents en erreur
- taille totale traitée
- durée du job
- date de début
- date de fin
- phase courante
- pourcentage d'avancement si disponible
- version de corpus concernée

Le prompt doit demander des métriques plus détaillées dès qu'elles sont réellement disponibles, par exemple :

- nombre de fichiers nouveaux, modifiés et supprimés dans le snapshot
- nombre de fragments / chunks produits
- nombre d'entités extraites
- nombre de relations extraites
- nombre de communautés générées
- temps passé par phase :
  - synchronisation
  - préparation documentaire
  - chunking
  - extraction
  - indexation
  - validation
  - publication
- débit moyen de traitement, par exemple documents par minute ou chunks par minute
- taille du snapshot source
- taille des artefacts générés
- nombre de retries déjà tentés
- worker ou pod ayant exécuté le job

Le prompt doit aussi exiger que ces métriques soient présentées de manière ergonomique dans l'interface, pas seulement dans les logs, avec par exemple :

- des cartes de synthèse
- une timeline ou un découpage par phases
- un tableau détaillé pour l'historique
- un panneau de détail d'un job
- une mise en évidence visuelle des valeurs anormales ou en erreur

Si certaines métriques ne sont pas disponibles de façon fiable, la solution doit :

- l'indiquer explicitement
- éviter d'afficher une fausse précision
- préférer une valeur absente à une valeur trompeuse

Le prompt doit aussi exiger une restitution claire des causes d'arrêt d'un job.

Il ne suffit pas d'afficher "failed" ou "stopped".

L'interface doit exposer au minimum :

- un motif synthétique lisible par un humain
- une catégorie d'échec, par exemple :
  - erreur d'authentification
  - source indisponible
  - quota ou rate limit
  - erreur de parsing documentaire
  - erreur d'indexation GraphRAG
  - erreur de stockage
  - annulation manuelle
  - timeout
- un détail technique consultable si besoin
- un lien ou panneau vers les logs détaillés

Le mécanisme de retry doit être encadré :

- visible uniquement quand il est cohérent
- idempotent autant que possible
- tracé dans l'historique
- associé à un nouveau job ou à une nouvelle tentative clairement identifiable
- impossible si le retry met en risque la cohérence d'une version publiée sans étape de validation adaptée

Le prompt doit imposer explicitement une règle de visibilité des indexations :

- rôle admin : vue globale sur tous les corpus, tous les jobs et tous les états
- rôle non admin : vue limitée aux corpus accessibles via ses groupes ou permissions directes
- aucune fuite de métadonnées sur l'existence, le volume ou l'état d'un corpus non autorisé
- les filtres, compteurs, tableaux de bord et exports doivent respecter ces mêmes règles

Le prompt doit exiger un état lisible du workflow, avec par exemple :

- `idle`
- `syncing`
- `snapshot_ready`
- `indexing`
- `validating`
- `published`
- `failed`

--------------------------------------------------

NOTIFICATIONS ET SUIVI DANS OPEN WEBUI

L'utilisateur doit pouvoir suivre l'état des indexations quelque part dans l'interface, et idéalement recevoir aussi une notification dans Open WebUI.

Tu dois t'appuyer sur les surfaces déjà observées dans la documentation locale Open WebUI disponible sur `http://localhost:3000/docs#/` et dans son backend existant.

Eléments clés déjà confirmés localement et à exploiter dans la conception :

- `POST /api/chat/completions`
- `POST /api/v1/chat/completions`
- routes de type `/api/v1/chats`
- routes de type `/api/v1/channels`
- route de configuration retrieval de type `/api/v1/retrieval/config`
- configuration web search exposée par le schéma `WebConfig`, avec notamment :
  - `ENABLE_WEB_SEARCH`
  - `WEB_SEARCH_ENGINE`
  - `SEARXNG_QUERY_URL`
- présence de logique de notification côté channels dans le backend Open WebUI

Le prompt doit demander une solution élégante qui privilégie les surfaces natives d'Open WebUI au lieu d'un mécanisme parallèle purement custom.

Solution attendue à challenger puis implémenter :

- créer un canal ou un chat système dédié aux notifications d'indexation
- poster des événements de type :
  - synchronisation démarrée
  - indexation démarrée
  - indexation à X %
  - échec avec résumé
  - publication réussie
- inclure un lien profond vers l'interface `mycorpus`
- prévoir une granularité par utilisateur, par groupe ou par corpus, selon ce qui est le plus cohérent

Le prompt doit aussi imposer que :

- la notification Open WebUI n'est pas le seul mécanisme de suivi
- l'interface de pilotage reste la référence détaillée
- les notifications Open WebUI servent d'alerte et de raccourci ergonomique

--------------------------------------------------

SELECTION ET UTILISATION DES CORPUS DANS OPEN WEBUI

Le système doit définir une UX simple pour requêter les bons corpus dans Open WebUI.

Tu dois comparer au minimum deux approches et justifier le choix retenu :

1. un alias / modèle Open WebUI par corpus
2. un modèle GraphRAG unique avec sélection explicite du corpus autorisé

La solution recommandée doit privilégier :

- un modèle unique ou une petite famille de modèles
- avec une sélection explicite du corpus ou d'un espace documentaire autorisé

car la stratégie "un modèle par corpus" devient vite ingérable à grande échelle.

Si une recherche multi-corpus est proposée, elle doit être :

- explicite
- limitée aux corpus autorisés
- désactivée par défaut si elle dégrade la sécurité ou la lisibilité

--------------------------------------------------

ARCHITECTURE TECHNIQUE RECOMMANDEE

Le repository à produire doit introduire, ou préparer explicitement, les composants suivants :

- `drive-connector`
- `corpus-manager-api`
- `corpus-manager-ui`
- `indexer-worker`
- `object storage` ou stockage versionné pour snapshots et artefacts
- `metadata database` pour les corpus, ACL et jobs

Architecture logique cible :

Source documentaire externe
↓
Connecteur de synchronisation
↓
Snapshot versionné
↓
Worker d'indexation GraphRAG
↓
Artefacts GraphRAG par corpus/version
↓
Publication d'une version active
↓
Bridge GraphRAG
↓
Open WebUI

Le prompt doit imposer une architecture compatible avec une montée en charge horizontale.

Cela signifie au minimum :

- APIs stateless autant que possible
- workers d'indexation découplés et parallélisables
- stockage persistant hors des pods
- files d'attente ou mécanismes de coordination compatibles multi-réplicas
- séparation claire entre plan de contrôle et plan d'exécution

Tu dois toutefois exiger une honnêteté technique composant par composant :

- ne pas affirmer qu'un composant est horizontalement scalable sans validation réelle
- documenter explicitement les composants réplicables et ceux qui imposent une contrainte particulière
- si une session, un verrou, un cache ou un stockage partagé est nécessaire, il doit être prévu explicitement

Le prompt doit demander une cible de scalabilité explicite, par exemple :

- plusieurs réplicas pour l'API de pilotage
- plusieurs workers d'indexation
- plusieurs réplicas pour le bridge GraphRAG si l'architecture de stockage et de cache le permet
- plusieurs pods `drive` uniquement si ce mode est réellement compatible avec ses dépendances et son stockage

Tu dois aussi imposer que le design évite :

- l'affinité forte à un pod unique pour les métadonnées
- les écritures locales non partagées comme source de vérité
- les jobs non traçables ou non rejouables en environnement multi-réplicas

--------------------------------------------------

EXIGENCES DE SECURITE

Le prompt doit imposer :

- authentification OIDC via Keycloak
- vérification du JWT côté services backend
- contrôle d'accès côté API et pas uniquement côté interface
- séparation stricte des artefacts par corpus
- logs d'audit minimum sur :
  - création de corpus
  - changement d'ACL
  - lancement d'indexation
  - publication de version
- secret management cohérent pour Docker et Kubernetes

Tu dois aussi prévoir des garde-fous :

- impossible d'interroger un corpus non autorisé en forgeant simplement un `corpus_id`
- impossible de publier une version partielle ou incomplète
- rollback possible vers une version active précédente

--------------------------------------------------

LOCAL DOCKER ET KUBERNETES

Le repository généré doit fonctionner :

- en local avec Docker Compose
- en Kubernetes

En local :

- la stack doit être testable sans infrastructure externe lourde
- un mode mock ou une source locale substituable au connecteur Drive est acceptable pour les tests si le vrai connecteur n'est pas trivialement testable
- mais le prompt doit aussi demander un vrai chemin de test avec `drive` lui-même, pas uniquement un mock
- ce chemin local doit permettre soit un lancement simple en conteneurs, soit un déploiement Kubernetes local avec un ou plusieurs pods `drive`
- le repository doit documenter clairement comment lancer ce `drive` local, comment y injecter quelques fichiers de test, et comment vérifier que la synchronisation GraphRAG fonctionne réellement
- si `drive` nécessite des dépendances annexes en local, celles-ci doivent être provisionnées ou explicitement documentées

En Kubernetes :

- les workers d'indexation doivent tourner en jobs ou workers séparés
- l'interface Corpus Manager doit être derrière Keycloak
- les artefacts doivent être persistés hors du cycle de vie des pods
- le prompt doit aussi prévoir un déploiement `drive` en cluster ou en cluster local, avec clarification des dépendances de stockage, base de données et sessions si plusieurs pods sont activés

--------------------------------------------------

API ET EVENEMENTS ATTENDUS

Le prompt doit demander des endpoints et surfaces cohérents, par exemple :

- `POST /api/corpora`
- `GET /api/corpora`
- `GET /api/corpora/{id}`
- `POST /api/corpora/{id}/sync`
- `POST /api/corpora/{id}/index`
- `POST /api/corpora/{id}/publish/{version}`
- `GET /api/corpora/{id}/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/logs`

Tu peux proposer un bus d'événements ou une file, mais la solution doit rester pragmatique et compatible avec un MVP réaliste.

--------------------------------------------------

OBSERVABILITE ET ETAT DANS L'INTERFACE

Le prompt doit exiger un vrai suivi visuel :

- file d'attente
- progression
- état final
- durée
- date de début
- date de fin
- cause d'échec synthétique

Le suivi doit être visible :

- dans le `Corpus Manager`
- et sous forme de notification synthétique dans Open WebUI

Une simple consultation de logs bruts ne suffit pas.

--------------------------------------------------

TESTS ET CRITERES D'ACCEPTATION

Le prompt doit exiger au minimum :

- tests unitaires du modèle ACL
- tests API pour création de corpus et lancement de job
- tests d'autorisation par groupe Keycloak
- test de non-régression : un utilisateur non autorisé ne voit ni ne requête un corpus privé
- test de cycle complet :
  - synchronisation
  - snapshot
  - indexation
  - publication
  - requête Open WebUI
- test de notification Open WebUI ou, si non automatisable proprement, validation d'un flux documenté et vérifiable

--------------------------------------------------

LIVRABLES ATTENDUS

Le repository généré doit inclure :

- le code applicatif
- la configuration Docker
- les manifests Kubernetes
- les scripts d'initialisation
- les tests
- la documentation
- les exemples de variables d'environnement
- les explications d'architecture et de sécurité

Le prompt doit aussi demander une mise à jour du README et de la documentation opérationnelle pour expliquer :

- comment connecter une source
- comment créer un corpus
- comment lancer une indexation
- comment suivre son état
- comment sont gérés les droits d'accès
- comment l'utilisateur retrouve les notifications dans Open WebUI

--------------------------------------------------

CONSIGNES DE QUALITE

Tu dois produire une solution :

- défendable techniquement
- cohérente avec les limites réelles d'Open WebUI, GraphRAG et Keycloak
- explicite sur ses hypothèses
- honnête sur ce qui est réellement implémenté et ce qui est seulement préparé

Si une idée est séduisante mais risquée ou trompeuse, tu dois l'amender explicitement au lieu de la suivre aveuglément.

Ne produis pas une architecture gadget.

Produis un système simple, propre, sécurisé et opérable.
