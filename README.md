# SentinelShop

A small shop (web page, REST API, order worker) wrapped in a secure delivery pipeline, observability, automatic attack response, Kubernetes, Terraform and Ansible. Everything runs locally, with no cloud.

## Quick start

Needs: Docker Engine with Compose v2, make, git, openssl. Optional: pre-commit.

    git clone <repo> sentinelshop && cd sentinelshop
    make up && make smoke

- `make up` creates `.env` with generated secrets if it is missing, then builds and starts the stack.
- The shop is on http://localhost:8080. If that port is busy, set `EDGE_PORT=8088` in `.env` and run `make up` again.
- After you change passwords in `.env`, run `make clean` first. Postgres only reads its password when the volume is created.
- `make clean` removes all containers and volumes. `make down` keeps the data.
- On a fresh clone, run `pre-commit install` to enable the secret-scanning hook.

## Layout

| Path | What it holds |
|---|---|
| services/ | application code and Dockerfiles |
| docker-compose.yml, docker-compose.monitoring.yml, docker-compose.detection.yml | the stack, in three layers |
| Makefile, scripts/ | every task is a make target; smoke test in scripts/ |
| Jenkinsfile (repo root), ci/ | pipeline definition and the Jenkins image |
| helm/shop/, gitops/ | Kubernetes chart and the production image tag |
| terraform/ | modules cluster and platform |
| ansible/ | roles hardening and backup |
| monitoring/ | Prometheus, Alertmanager, Loki, Alloy, alerts, runbooks, playbooks, Grafana (dashboards in monitoring/grafana/dashboards) |
| detection/ | Wazuh rules (detection/wazuh/local_rules.xml), attacker, responder |
| chaos/ | runtime fault flags for the drill |
| evidence/ | proof for each task |
| docs/ | architecture diagram, RCA, spec |
