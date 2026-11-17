# AI log

Claude Code wrote the application code (API, worker, web page, tests). It was not used for the infrastructure side. Each entry says what I asked, what came back, what I changed and how I checked.

## My setup

I used Claude Code for the application code only. I also used a separate chat assistant to learn DevSecOps concepts, and it did not write any of the infrastructure files.

I set up Claude Code before it wrote anything. These files are local working files and are not in the repo, so `contracts/`, `docs/` and `.claude/` paths mentioned in this log are not in the repository. I can show them in the live review.

- **Project rules.** A `CLAUDE.md` file held the rules every session started from: the contracts are frozen, the infrastructure files are off limits, and work is done in small steps with a report at the end.
- **Two sub-agents.** `app-builder` wrote the code. `verifier` reviewed it and did not write code. Splitting the roles stopped the agent that wrote the code from marking its own work as correct.
- **Two commands.** `task-start` loaded the rules and contracts before a step. `verify` ran the checks after it, so the checks were the same each time.
- **Permissions.** `.claude/settings.json` limited what the agent could run and edit.
- **Contracts.** Written agreements on ports, API shapes, log fields, metric names, detection and chaos behaviour. I wrote them before the code existed so the application matched the infrastructure I was building in parallel. The agent had to follow them, and if one was wrong it proposed a change and I decided.

The verifier's report was never proof by itself. I trusted the unit tests, the smoke test on the running stack, the CI pipeline and the scans.

## How I worked

I set the rules before it started. The API contracts in `contracts/` were frozen and it had to match them exactly. It was told which files it must never touch (Dockerfiles, compose files, Makefile, pipeline, monitoring, detection, Kubernetes, Terraform, Ansible, README and this log). It worked one step per session, and each step ended with a short report: files changed, test results, contract lines checked and what was not verified. It committed only when the tests passed. When something conflicted with a contract it did not change it. It wrote a proposal in `docs/CONTRACT-CHANGES.md` for me to decide.

## 1. API and its tests

Asked for the catalog API in steps: skeleton with env config, JSON logs, products and metrics (`2752319`), then orders, login, search and readyz (`5e24eb0`), then tests for those including parameterised SQL (`31b0b7d`). I accepted the structure. I checked it with the unit tests, then with the smoke test against the running stack.

## 2. Small fixes found after the first versions

The first versions needed three fixes. The Redis client had no timeouts, so with Redis down a request would hang, while the contract says 503 and a live process. I had it set 2 second connect and socket timeouts (`0c621a5`). An invalid `LOG_LEVEL` is now rejected at startup (`751f61d`). The bcrypt cost for the demo users was raised to 10 (`450d991`).

## 3. Order worker

Asked for a worker that takes orders off the Redis queue and survives a normal stop (`b32e524`). It handles SIGTERM, so a stopped worker finishes the order it holds. I accepted it. One limit remains and is in the README: a worker killed with SIGKILL or out of memory loses the one order it was processing.

## 4. Login timing leak

During its verification step, Claude Code found that a login for an unknown username returns faster than a wrong password for a real user, because bcrypt only runs when a row matches. That lets someone find valid usernames. The contract pins the query, so it did not change the code. It wrote a proposal with three options in `docs/CONTRACT-CHANGES.md`. I decided to accept the risk and document it, since brute force on login is detected and blocked at the edge and the users are demo accounts.

## 5. Web page redesign

Asked for a better-looking shop page with product cards, an orders panel, a login view and friendly error messages (`dcdf577`). I accepted the layout. The Order button came out squashed, which was fixed. The commit also carried an AI co-author line that I removed before merging. I checked it with the tests, the real stack and the browser.

## 6. Chaos fault flags

Asked for four fault flags (latency, error rate, slow database writes, memory leak) read only from a runtime file (`ed33257`, `1408f6c`). My first prompt also asked for a startup log line listing the active flags. That would have shown the fault in the logs and spoiled the blind drill, so I removed that request before it was built.


## 7. Detection rules, the integration and manual unblock

The first Wazuh rules did not work. Wazuh rejected a rule that matched the static `status` field and needed the `<status>` tag. The counting rules did not fire because the level 0 base rules are not counted, and `frequency` fires on the Nth event, so the brute-force rule fired at event 8 with frequency 8. I found each of these with `wazuh-logtest` and a replay of the log lines, and fixed them one by one. The first live run raised the alert but nothing was blocked. `ossec.log` said Wazuh could not execute the integration script, because the script was not executable by the user the integration runs as. I changed its mode to 755 and the next run blocked the attacker. Later I saw that unblocking by editing the blocklist file would be undone by the responder's memory, and restarting it would wipe the audit log, so I added a `POST /unblock` endpoint (`bf91ccf`). I checked all of it with `evidence/detection/attacks-summary.txt` (each attack gives one alert, attacker 403, normal client 200), `dedup-window.txt` (a repeat inside 300 seconds gives no second alert) and the false-positive file (zero alerts for 6001 normal requests).
