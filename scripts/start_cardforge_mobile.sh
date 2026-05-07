#!/usr/bin/env bash
set -euo pipefail
: "${CARDFORGE_UI_PASSWORD:?Set CARDFORGE_UI_PASSWORD before starting mobile mode}"
cardforge mobile serve --password "$CARDFORGE_UI_PASSWORD"
