SHELL := /bin/bash

.PHONY: init up down logs index smoke test security-test deploy-k8s report

init:
	./deploy/prepare-env.sh
	./scripts/init_graphrag.sh

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f bridge openwebui pipelines

index:
	./scripts/index_corpus.sh

smoke:
	./smoke-tests.sh

test:
	./integration-tests.sh

security-test:
	./penetration-tests.sh

deploy-k8s:
	./deploy/deploy-k8s.sh

report:
	./report.sh

