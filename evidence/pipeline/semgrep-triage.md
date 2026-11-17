# Semgrep triage

## Finding
- Rule: semgrep-rules.sentinelshop-sql-string-building (custom rule, severity Blocking)
- File: services/catalog-api/app/demo_search.py, line 3
- Code: cur.execute(f"SELECT id, name FROM products WHERE name LIKE '%{term}%'")
- Seen on branch demo/insecure, pipeline stage SAST, `make sast` exit 2 (log: demo-fail-sast.log)

## Verdict
True positive. The search term goes into the SQL string, so a crafted term changes the query (SQL injection, OWASP A03).

## Fix
- Commit 8ca21e9 on demo/fixed: "fix: pass search values as query parameters"
- The value is passed as a parameter to cur.execute, so the driver escapes it
- The same rule then reports 0 findings and the stage passes (green run: demo-green-after-fix.log)

## Decision
- Fixed in code instead of suppressed because the finding is real: the search term was concatenated into the SQL string, and a parameterized query removes the flaw with a one-line change. A suppression is only for false positives or risks accepted on purpose, and this was neither.
- Only ERROR-level findings stop the build (`--severity ERROR --error`), because an injection flaw should never reach an image. Medium and low findings run in a separate advisory pass (commit 4e2698f) that reports them without failing the pipeline, so the team still sees them but is not blocked by noise.

## Related
- Wider advisory scan: semgrep-wide-scan.txt
- Dependency finding on the same branch handled by upgrade (commit f364a22); the fake secret was suppressed with a written reason (commit 1ac91e8)
