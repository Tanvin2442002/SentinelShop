.RECIPEPREFIX = >
.DEFAULT_GOAL := up
COMPOSE := docker compose

.PHONY: env up down clean logs ps smoke

env:
> test -f .env || (cp .env.example .env \
>   && sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 16)/; s/^SECRET_KEY=.*/SECRET_KEY=$$(openssl rand -hex 32)/; s/^GRAFANA_ADMIN_PASSWORD=.*/GRAFANA_ADMIN_PASSWORD=$$(openssl rand -hex 12)/" .env \
>   && echo "created .env with generated secrets")

up: env
> $(COMPOSE) up -d --build --wait --wait-timeout 180
> @echo "stack is up on the port set by EDGE_PORT in .env (default 8080)"

down:
> $(MON) down

clean:
> $(MON) down -v

logs:
> $(COMPOSE) logs -f --tail 50

ps:
> $(COMPOSE) ps

smoke:
> bash scripts/smoke-test.sh


GITLEAKS := zricethezav/gitleaks:v8.30.1
SEMGREP  := semgrep/semgrep:1.184.0
TRIVY    := aquasec/trivy:0.76.2
HADOLINT := hadolint/hadolint:v2.15.1
UID_GID  := $(shell id -u):$(shell id -g)
SERVICES := catalog-api order-worker web

.PHONY: secrets lint sast scan-config ci

secrets:
secrets:
> @test -z "$$(git ls-files .env)" || (echo "FAIL: .env is tracked by git" && exit 1)
> @test -z "$$(git log --all --oneline -- .env)" || (echo "FAIL: .env appears in git history" && exit 1)
> docker run --rm --user $(UID_GID) -v "$(CURDIR):/repo" $(GITLEAKS) git -v --redact -c /repo/.gitleaks.toml /repo
> docker run --rm --user $(UID_GID) -v "$(CURDIR):/repo" $(GITLEAKS) dir -v --redact -c /repo/.gitleaks.toml /repo

lint:
> for s in $(SERVICES); do echo "== $$s"; docker run --rm -i $(HADOLINT) < services/$$s/Dockerfile || exit 1; done

sast:
> docker run --rm -v "$(CURDIR):/src" -w /src $(SEMGREP) semgrep scan --config semgrep-rules/ --config p/python --config p/dockerfile --severity ERROR --metrics=off --error services
> @echo "--- advisory pass: all severities, does not fail the build ---"
> docker run --rm -v "$(CURDIR):/src" -w /src $(SEMGREP) semgrep scan --config p/security-audit --config p/owasp-top-ten --config p/dockerfile --metrics=off services


scan-config:
> docker run --rm -v "$(CURDIR):/src" -v trivy-cache:/root/.cache/ $(TRIVY) config --severity HIGH,CRITICAL --exit-code 1 /src

ci: secrets lint sast scan-config

REGISTRY ?= localhost:5000
TAG      ?= $(shell git rev-parse --short HEAD)

.PHONY: registry build scan-images push

registry:
> docker inspect -f '{{.State.Running}}' registry 2>/dev/null | grep -q true || (docker rm -f registry 2>/dev/null; docker run -d --restart unless-stopped --name registry -p 127.0.0.1:5000:5000 registry:2.8.3)

build:
> TAG=$(TAG) $(COMPOSE) build --pull --no-cache

scan-images:
> for s in $(SERVICES); do echo "== $$s:$(TAG)"; \
>   docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ $(TRIVY) image --severity HIGH --ignore-unfixed --exit-code 0 --quiet $(REGISTRY)/$$s:$(TAG); \
>   docker run --rm -v /var/run/docker.sock:/var/run/docker.sock -v trivy-cache:/root/.cache/ $(TRIVY) image --severity CRITICAL --ignore-unfixed --exit-code 1 --quiet $(REGISTRY)/$$s:$(TAG) || exit 1; \
> done

push: registry
> for s in $(SERVICES); do docker push $(REGISTRY)/$$s:$(TAG) || exit 1; done

GITOPS_DIR ?= $(HOME)/Documents/Projects/sentinelShop-gitops

.PHONY: gitops

gitops:
> sed -i 's/^tag: .*/tag: "$(TAG)"/' $(GITOPS_DIR)/values-prod.yaml
> git -C $(GITOPS_DIR) diff --quiet || git -C $(GITOPS_DIR) -c user.name=sentinelshop-ci -c user.email=ci@localhost commit -q -am "chore: set production image tag to $(TAG)"

MON          := $(COMPOSE) -f docker-compose.yml -f docker-compose.monitoring.yml
MON_SERVICES := prometheus cadvisor node-exporter loki alloy grafana alertmanager alert-receiver

.PHONY: mon-up mon-down mon-ps
mon-up:
> $(MON) up -d $(MON_SERVICES)

mon-down:
> $(MON) rm -sf $(MON_SERVICES)

mon-ps:
> $(MON) ps