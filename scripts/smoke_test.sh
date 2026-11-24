#!/usr/bin/env bash
# ./scripts/smoke_test.sh <base-url> [identity-token]
set -euo pipefail

URL="${1:?usage: smoke_test.sh <base-url> [token]}"
TOKEN="${2:-}"
AUTH=()
[[ -n "$TOKEN" ]] && AUTH=(-H "Authorization: Bearer $TOKEN")

curl -fsS "${AUTH[@]}" "$URL/health" | grep -q '"ok"'

resp=$(curl -fsS "${AUTH[@]}" -H "Content-Type: application/json" -H "X-User-Id: u-smoke" \
  -d '{"session_id":"smoke","message":"How do I factory reset the Kestrel hub?"}' \
  "$URL/chat")
echo "$resp"

python3 - "$resp" <<'EOF'
import json, sys
r = json.loads(sys.argv[1])
assert not r["handed_off"], r
assert any(c.startswith("hub_h1#") for c in r["citations"]), r
assert "15 seconds" in r["answer"], r
print("smoke ok")
EOF
