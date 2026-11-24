#!/usr/bin/env bash
# Load the sample device fleet into BigQuery so the deployed agent has
# something to look up. In a real deployment this table is fed by telemetry.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"

tmp=$(mktemp)
python3 -c "
import json
for d in json.load(open('data/device_status.json'))['devices']:
    print(json.dumps(d))
" > "$tmp"

bq --project_id="$GCP_PROJECT" load --replace --source_format=NEWLINE_DELIMITED_JSON \
  support_agent.device_status "$tmp"
rm -f "$tmp"
echo "loaded device_status"
