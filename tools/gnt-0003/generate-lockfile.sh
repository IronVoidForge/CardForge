#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="${1:-$PWD/.gnt-0003-workspace}"
rm -rf "$ROOT"
mkdir -p "$ROOT/apps/client" "$ROOT/packages"/{application,config,contracts,data,domain,feed,player,sync,testkit,ui}

cat > "$ROOT/package.json" <<'JSON'
{
  "name": "@spoolmark/workspace",
  "version": "0.0.0",
  "private": true,
  "packageManager": "pnpm@11.20.0",
  "engines": { "node": ">=22.13.1" },
  "devDependencies": { "typescript": "~6.0.3" }
}
JSON
cat > "$ROOT/pnpm-workspace.yaml" <<'YAML'
packages:
  - "apps/*"
  - "packages/*"

peersSuffixMaxLength: 32
YAML
cat > "$ROOT/.npmrc" <<'EOF'
node-linker=hoisted
shared-workspace-lockfile=true
strict-peer-dependencies=true
link-workspace-packages=true
prefer-workspace-packages=true
EOF
cat > "$ROOT/apps/client/package.json" <<'JSON'
{
  "name": "@spoolmark/client",
  "version": "0.0.0",
  "private": true,
  "main": "expo-router/entry",
  "dependencies": {
    "@spoolmark/application": "workspace:*",
    "@spoolmark/contracts": "workspace:*",
    "@spoolmark/ui": "workspace:*",
    "expo": "~57.0.9",
    "expo-constants": "~57.0.8",
    "expo-linking": "~57.0.4",
    "expo-router": "~57.0.9",
    "expo-status-bar": "~57.0.1",
    "react": "19.2.3",
    "react-dom": "19.2.3",
    "react-native": "0.86.2",
    "react-native-safe-area-context": "~5.7.0",
    "react-native-screens": "~4.26.0",
    "react-native-web": "~0.21.0"
  },
  "devDependencies": {
    "@types/react": "~19.2.2",
    "typescript": "~6.0.3"
  }
}
JSON

write_package() {
  local name="$1"
  local dependencies="${2:-}"
  if [[ -n "$dependencies" ]]; then
    cat > "$ROOT/packages/$name/package.json" <<JSON
{
  "name": "@spoolmark/$name",
  "version": "0.0.0",
  "private": true,
  "dependencies": $dependencies
}
JSON
  else
    cat > "$ROOT/packages/$name/package.json" <<JSON
{
  "name": "@spoolmark/$name",
  "version": "0.0.0",
  "private": true
}
JSON
  fi
}

CORE='{"@spoolmark/contracts":"workspace:*","@spoolmark/domain":"workspace:*"}'
ADAPTER='{"@spoolmark/application":"workspace:*","@spoolmark/contracts":"workspace:*","@spoolmark/domain":"workspace:*"}'
write_package application "$CORE"
write_package config
write_package contracts
write_package data "$ADAPTER"
write_package domain
write_package feed "$ADAPTER"
write_package player "$ADAPTER"
write_package sync "$ADAPTER"
write_package testkit "$ADAPTER"
write_package ui '{"@spoolmark/contracts":"workspace:*"}'

cd "$ROOT"
pnpm install --lockfile-only
pnpm install --frozen-lockfile
pnpm list --depth 0 --recursive
