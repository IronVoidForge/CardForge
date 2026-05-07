from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path

from cardforge.config import AppSettings, load_settings


@dataclass(frozen=True)
class MobileLauncherResult:
    url: str
    path: Path


def guess_lan_ip() -> str:
    """Return a likely LAN IP without sending data to the internet."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        except OSError:
            return "127.0.0.1"


def mobile_url(*, host: str | None = None, port: int = 8765, https: bool = False) -> str:
    selected = host or guess_lan_ip()
    if selected in {"0.0.0.0", "::"}:
        selected = guess_lan_ip()
    scheme = "https" if https else "http"
    return f"{scheme}://{selected}:{int(port)}/m"


def launcher_html(url: str) -> str:
    escaped = url.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta http-equiv=\"refresh\" content=\"0; url={escaped}\">
  <title>Open CardForge Mobile</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: system-ui, sans-serif; background: #f4efe6; color: #241f2f; }}
    main {{ width: min(560px, calc(100vw - 32px)); padding: 28px; border-radius: 24px; background: #fffaf0; box-shadow: 0 18px 44px rgba(38, 28, 55, .14); }}
    a {{ color: #472184; font-weight: 800; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <p>Opening CardForge Mobile…</p>
    <h1><a href=\"{escaped}\">{escaped}</a></h1>
    <p>If this file does not open the app, make sure the workstation server is running and your device is on the same LAN or VPN.</p>
  </main>
</body>
</html>
"""


def write_mobile_launcher(url: str, *, settings: AppSettings | None = None, output: Path | None = None) -> MobileLauncherResult:
    active_settings = settings or load_settings()
    path = output or (active_settings.workspace_root / "CardForge_Mobile_Launcher.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(launcher_html(url), encoding="utf-8")
    return MobileLauncherResult(url=url, path=path)
