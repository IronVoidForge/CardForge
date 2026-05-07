@echo off
if "%CARDFORGE_UI_PASSWORD%"=="" (
  echo Set CARDFORGE_UI_PASSWORD before starting mobile mode.
  exit /b 1
)
cardforge mobile serve --password "%CARDFORGE_UI_PASSWORD%"
