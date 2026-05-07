from __future__ import annotations

import os
from enum import Enum

import typer
import uvicorn

from cardforge.cli.bootstrap import ensure_db
from cardforge.services.mobile.mobile_launcher import mobile_url

app = typer.Typer(help="Local operator UI commands")


class UIMode(str, Enum):
    desktop = "desktop"
    mobile = "mobile"
    both = "both"


@app.command("serve")
def serve_ui(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind. Use 0.0.0.0 for LAN access."),
    port: int = typer.Option(8765, "--port", help="Port to bind."),
    mode: UIMode = typer.Option(UIMode.desktop, "--mode", help="desktop, mobile, or both."),
    mobile: bool = typer.Option(False, "--mobile", help="Compatibility alias for --mode mobile."),
    password: str = typer.Option("", "--password", help="Optional UI password. Also enables login protection."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable login protection."),
) -> None:
    """Serve the CardForge local web UI.

    Desktop and mobile pages can be served from the same process.  Use
    ``--mode both --host 0.0.0.0`` for a PC browser plus phone/tablet access on
    your LAN or VPN.
    """
    ensure_db()
    selected_mode = UIMode.mobile if mobile else mode
    bind_host = "0.0.0.0" if selected_mode in {UIMode.mobile, UIMode.both} and host == "127.0.0.1" else host
    os.environ["CARDFORGE_UI_MOBILE_ONLY"] = "true" if selected_mode == UIMode.mobile else "false"
    base_url = f"http://{bind_host}:{port}"
    if bind_host in {"0.0.0.0", "::"}:
        base_url = mobile_url(host=bind_host, port=port).rsplit("/m", 1)[0]
    os.environ["CARDFORGE_UI_PUBLIC_BASE_URL"] = base_url
    if password:
        os.environ["CARDFORGE_UI_PASSWORD"] = password
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "true"
    elif no_auth:
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "false"
    typer.echo(f"CardForge desktop UI: {base_url}/")
    typer.echo(f"CardForge mobile UI:  {base_url}/m")
    if selected_mode == UIMode.mobile:
        typer.echo("Mobile-only mode is active; / redirects to /m.")
    elif selected_mode == UIMode.both:
        typer.echo("Both desktop and mobile routes are active.")
    uvicorn.run("cardforge.web.app:app", host=bind_host, port=port, reload=False)
