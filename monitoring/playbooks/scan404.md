# Playbook: Path scanning (many 404s)

## Trigger

- Wazuh rule `shop-scan-404` (id 100114), level 7 (medium).
- 15 requests answered 404 from one source within 30 seconds.
- MITRE ATT&CK T1595.003 (Active Scanning: Wordlist Scanning). OWASP Top 10 2021 A05:2021 Security Misconfiguration.

## Triage

Shortcut used below: `D="docker compose -f docker-compose.yml -f docker-compose.detection.yml"`

1. Read the audit line and the case record: `$D exec -T responder sh -c 'tail -n 5 /data/audit.jsonl; ls /data/cases'`, then `$D exec -T responder cat /data/cases/<case_id>.json`.
2. See what the source sent: `$D exec -T wazuh-manager sh -c 'grep "<ip>" /var/log/shop/edge.json | tail -n 30'`.
3. Read the list of paths probed and the user agent. Check whether any of those paths returned 200, which would mean something sensitive is exposed.
4. Check the enrichment in the case (reputation score and label). Confirm the source is not a known tester or an internal client that belongs on the allowlist.

## Automatic action

Wazuh raises the alert and the `custom-responder` integration posts it to the responder. The responder skips allowlisted sources, ignores a source that is already blocked, and otherwise writes `deny <ip>;` into the blocklist for `BLOCK_TTL_SECONDS` (default 600 s). The edge reloads within about a second. The responder then checks that the attacker gets 403 and a normal client still gets 200, writes a case record and writes one audit line (`blocked`). Wazuh stays silent for this rule for the next 300 s.

## Manual follow-up

Make sure no probed path exposes a real file or an admin page. Review which paths a real client would ever need.

## Unblock

The block ends by itself after the TTL (audit line `expired`). To release a source earlier:

    $D exec -T responder wget -qO- --post-data='{"ip":"<ip>"}' http://127.0.0.1:8088/unblock

Wait about 2 seconds for the edge to reload, then check that the source reaches the shop again. The release is recorded in the audit file as `expired` with reason `manual unblock`. List current blocks with `$D exec -T responder wget -qO- http://127.0.0.1:8088/blocks`.

## Escalate

Escalate to the on-call security engineer when:

- A probed path returned 200 and it is not part of the shop.
- The source is an internal or allowlisted address.
- The same source comes back after the block expired, or several sources trigger the rule.
- The audit shows `error`, or the case shows a verification other than attacker 403 and normal client 200.
