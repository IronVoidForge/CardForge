from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cardforge.config import AppSettings, load_settings
from cardforge.services.mobile.mobile_launcher import mobile_url, write_mobile_launcher


@dataclass(frozen=True)
class LauncherBundle:
    directory: Path
    files: list[Path]
    mobile_url: str


def write_operator_launchers(
    *,
    host: str | None = None,
    port: int = 8765,
    output_dir: Path | None = None,
    settings: AppSettings | None = None,
) -> LauncherBundle:
    active_settings = settings or load_settings()
    target_url = mobile_url(host=host, port=port)
    directory = output_dir or (active_settings.workspace_root / "launchers")
    directory.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    files.append(_write(directory / "Start_CardForge_Both.bat", _windows_start_script(mode="both", port=port)))
    files.append(_write(directory / "Start_CardForge_Mobile.bat", _windows_start_script(mode="mobile", port=port)))
    files.append(_write(directory / "Start_CardForge_Desktop.bat", _windows_start_script(mode="desktop", port=port)))
    files.append(_write(directory / "Start_CardForge_Both.sh", _posix_start_script(mode="both", port=port), executable=True))
    files.append(_write(directory / "Start_CardForge_Mobile.sh", _posix_start_script(mode="mobile", port=port), executable=True))
    files.append(_write(directory / "Start_CardForge_Desktop.sh", _posix_start_script(mode="desktop", port=port), executable=True))
    files.append(write_mobile_launcher(target_url, settings=active_settings, output=directory / "Open_CardForge_Mobile.html").path)
    files.append(_write(directory / "README.txt", _readme(target_url, port=port)))
    return LauncherBundle(directory=directory, files=files, mobile_url=target_url)


def _write(path: Path, text: str, *, executable: bool = False) -> Path:
    path.write_text(text, encoding="utf-8", newline="\n")
    if executable:
        path.chmod(path.stat().st_mode | 0o111)
    return path


def _windows_start_script(*, mode: str, port: int) -> str:
    auth_hint = (
        "echo.\r\n"
        "echo Enter a local UI password. Leave blank only on a private/offline dev machine.\r\n"
        "set /p CF_PASSWORD=CardForge UI password: \r\n"
        "if not \"%CF_PASSWORD%\"==\"\" (set CF_AUTH=--password \"%CF_PASSWORD%\") else (set CF_AUTH=--no-auth)\r\n"
    )
    return f"""@echo off
setlocal
cd /d "%~dp0\\..\\.."
if exist ".venv\\Scripts\\activate.bat" call ".venv\\Scripts\\activate.bat"
{auth_hint}echo.
echo Starting CardForge in {mode} mode on port {port}...
echo Desktop: http://localhost:{port}/
echo Mobile:  http://YOUR-PC-IP:{port}/m
echo.
python -m cardforge ui serve --mode {mode} --host 0.0.0.0 --port {port} %CF_AUTH%
pause
"""


def _posix_start_script(*, mode: str, port: int) -> str:
    return f"""#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/../.."
if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi
printf 'CardForge UI password (leave blank only on a private/offline dev machine): '
IFS= read -r CF_PASSWORD || CF_PASSWORD=""
if [ -n "$CF_PASSWORD" ]; then
  CF_AUTH="--password $CF_PASSWORD"
else
  CF_AUTH="--no-auth"
fi
echo "Starting CardForge in {mode} mode on port {port}..."
echo "Desktop: http://localhost:{port}/"
echo "Mobile:  http://YOUR-PC-IP:{port}/m"
# shellcheck disable=SC2086
python -m cardforge ui serve --mode {mode} --host 0.0.0.0 --port {port} $CF_AUTH
"""


def _readme(url: str, *, port: int) -> str:
    return f"""CardForge launchers
====================

Double-click one of the Start_CardForge_*.bat files on Windows, or run the .sh files on macOS/Linux.

Recommended:
  Start_CardForge_Both.bat

Then open:
  Desktop: http://localhost:{port}/
  Mobile:  {url}

If the mobile URL does not work, replace the IP address with your workstation LAN/VPN IP.
Your phone/tablet must be on the same Wi-Fi/VPN as the workstation.

Open_CardForge_Mobile.html is a tap/click launcher that points to the current guessed mobile URL.
It does not start the Python server; start CardForge on the workstation first.
"""
