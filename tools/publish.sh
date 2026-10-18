#!/usr/bin/env bash
# Publish the five showcase bundles to the Hugging Face Hub from the VM.
# Usage: publish.sh [--dry] ; expects ~/showcase/{bundles,work,.venv}, HF_TOKEN in the environment (never printed),
# and optionally COLLECTION=<owner/slug> to add each dataset to a Hub collection.
set -euo pipefail
cd ~/showcase
DRY=${1:-}
PY=~/showcase/.venv/bin/python; AE=~/showcase/.venv/bin/agent-env
mkdir -p cards episodes datasets
for app in grafana gitea nocodb mattermost ghost; do
  title=$($PY -c "import json;print(json.load(open('work/tools/apps.json'))['$app']['title'])")
  license=$($PY -c "import json;print(json.load(open('work/tools/apps.json'))['$app']['license'])")
  authors=$($PY -c "import json;print(json.load(open('work/tools/apps.json'))['$app']['authors'])")
  repo=$($PY -c "import json;print(json.load(open('work/tools/apps.json'))['$app']['repo'])")
  hflic=$($PY -c "import json;print(json.load(open('work/tools/apps.json'))['$app']['hf_license'])")
  $PY work/tools/episode_stats.py --db ~/.local/state/agent-env/document_store/local.db --bundle-path ~/showcase/bundles/$app --out episodes/$app.json
  $PY work/tools/make_card.py --app $app --title "$title" --license "$license" --authors "$authors" --repo "$repo" \
      --bundle bundles/$app --summary work/apps/SUMMARY.json --episodes episodes/$app.json --apps work/tools/apps.json --export-pr 4999 --out cards/$app.md --template work/cards/TEMPLATE.md
  if [ "$DRY" = "--dry" ]; then
    $AE hf publish bundles/$app --name $app --out datasets/$app --runs all --reward retrieval --license $hflic --card-note cards/$app.md
    echo "$app: dataset written to datasets/$app ($(du -sh datasets/$app | cut -f1))"
  else
    $AE hf publish bundles/$app --name $app --repo earakely-scale/$repo --runs all --reward retrieval --license $hflic --card-note cards/$app.md --tag v0.1.0 ${COLLECTION:+--collection "$COLLECTION"}
    echo "$app: published to earakely-scale/$repo"
  fi
done
