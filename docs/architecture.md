# Architecture

Colours: blue is the public entry, green is application services, orange is data, purple is observability, red is security, grey is delivery tooling.

## Runtime view

```mermaid
flowchart LR
  user(["Browser or client"]):::ext -->|1 request| edge

  subgraph app["Application: docker compose, network shop-net"]
    edge["edge<br/>nginx: real IP, trace id, blocklist"]:::entry
    web["web<br/>static page"]:::svc
    api["catalog-api<br/>REST and queue producer"]:::svc
    redis[("redis<br/>order queue")]:::data
    worker["order-worker x2<br/>PENDING to COMPLETED"]:::svc
    pg[("postgres<br/>products, users, orders")]:::data
    edge --> web
    edge -->|2 /api| api
    api -->|3 read and write| pg
    api -->|4 enqueue order| redis
    redis -->|5 dequeue| worker
    worker -->|6 update status| pg
  end

  subgraph obs["Observability"]
    prom["prometheus<br/>metrics and alert rules"]:::obs
    cadv["cadvisor and node-exporter"]:::obs
    alloy["alloy<br/>log shipper"]:::obs
    loki["loki<br/>logs"]:::obs
    graf["grafana<br/>dashboards"]:::obs
    am["alertmanager"]:::obs
    recv["alert-receiver<br/>webhook"]:::obs
    prom -.->|scrape| api
    prom -.->|scrape| worker
    prom -.->|scrape| cadv
    alloy --> loki
    graf --> prom
    graf --> loki
    prom -->|firing alerts| am
    am --> recv
  end
  app -.->|container logs| alloy

  subgraph det["Detection and response"]
    wazuh["wazuh manager<br/>rules tagged MITRE and OWASP"]:::sec
    resp["responder<br/>allowlist, block, expire"]:::sec
    attacker["attacker<br/>test traffic"]:::sec
    edge -->|JSON access log| wazuh
    wazuh -->|alert| resp
    resp -->|blocklist file, nginx reload| edge
    attacker --> edge
  end

  classDef ext fill:#f1f5f9,stroke:#64748b,color:#0f172a
  classDef entry fill:#e0ecff,stroke:#2563eb,stroke-width:2px,color:#0b2a66
  classDef svc fill:#e6f7ee,stroke:#16a34a,color:#064e2b
  classDef data fill:#fff1db,stroke:#d97706,color:#5c3305
  classDef obs fill:#efe9ff,stroke:#7c3aed,color:#2e1065
  classDef sec fill:#ffe8e6,stroke:#dc2626,color:#6b1111
  classDef ci fill:#eceff3,stroke:#475569,color:#1e293b
  classDef iac fill:#e3f6f8,stroke:#0891b2,color:#083344
  style app fill:#f8fafc,stroke:#94a3b8,stroke-dasharray:5 4
  style obs fill:#faf8ff,stroke:#c4b5fd,stroke-dasharray:5 4
  style det fill:#fff8f7,stroke:#fca5a5,stroke-dasharray:5 4
```

## Delivery and infrastructure

```mermaid
flowchart LR
  dev(["Developer"]):::ext --> hook["pre-commit<br/>gitleaks"]:::sec
  hook --> repo[("git repo")]:::data
  repo --> jenkins["Jenkins :8081"]:::ci

  subgraph pipe["Pipeline: it only calls make targets"]
    checks["checks<br/>secrets, lint, SAST, image scan, helm lint, k8s scan"]:::ci
    build["build images<br/>tag is the short git SHA"]:::ci
    jenkins --> checks --> build
  end

  build --> reg[("local registry :5000")]:::data
  build -->|writes tag| gitops["gitops repo<br/>values-prod.yaml"]:::data
  gitops -->|manual: make deploy STAGE=prod| cluster
  reg --> cluster

  subgraph cluster["k3d cluster shop: helm chart"]
    traefik["Traefik ingress"]:::entry --> kweb["web"]:::svc
    traefik --> kapi["catalog-api"]:::svc
    kapi --> kdata[("postgres and redis<br/>StatefulSets")]:::data
    kworker["order-worker"]:::svc --> kdata
  end

  subgraph iac["Infrastructure as code"]
    tf["Terraform<br/>cluster and platform modules"]:::iac --> tfc["k3d cluster shop-tf<br/>namespace, quota, limits, default-deny"]:::iac
    ans["Ansible<br/>hardening and backup roles"]:::iac --> target["Ubuntu target container<br/>key-only SSH, ufw, nightly pg_dump"]:::iac
  end

  classDef ext fill:#f1f5f9,stroke:#64748b,color:#0f172a
  classDef entry fill:#e0ecff,stroke:#2563eb,stroke-width:2px,color:#0b2a66
  classDef svc fill:#e6f7ee,stroke:#16a34a,color:#064e2b
  classDef data fill:#fff1db,stroke:#d97706,color:#5c3305
  classDef sec fill:#ffe8e6,stroke:#dc2626,color:#6b1111
  classDef ci fill:#eceff3,stroke:#475569,color:#1e293b
  classDef iac fill:#e3f6f8,stroke:#0891b2,color:#083344
  style pipe fill:#f8fafc,stroke:#94a3b8,stroke-dasharray:5 4
  style cluster fill:#f6fff9,stroke:#86efac,stroke-dasharray:5 4
  style iac fill:#f3fcfd,stroke:#67e8f9,stroke-dasharray:5 4
```
