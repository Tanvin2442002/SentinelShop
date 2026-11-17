# Evidence

Output captured from real runs. Each folder maps to one task.

| Folder | Task | What is inside |
|---|---|---|
| hardening/ | Compose stack and hardening | Run logs, make cycle and backup proof |
| pipeline/ | CI/CD pipeline | Failing demo runs (CVE, SAST, secret history), pre-commit block, green run after the fix, Semgrep triage, hadolint and Trivy log, SHA tag and gitops proof, clean-checkout run |
| k8s/ | Kubernetes with Helm | Fresh cluster cycle, network policy before and after |
| terraform/ | Terraform and Ansible | Apply, verify and destroy logs |
| observability/ | Observability | Alert firing in Alertmanager and the receiver log with its runbook link |
| detection/ | Detection and response | Five attack cases, Wazuh alerts, responder audit log, false-positive run, dedup window, expiry |
| chaos/ | Chaos and RCA | Baseline and incident screenshots, k6 baseline, timeline, queries, rule that fired |

Failing runs on pipeline/ come from demo/insecure, which carries planted fake flaws and is never merged. The green run comes from demo/fixed.
