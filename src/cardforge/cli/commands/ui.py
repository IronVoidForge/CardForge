from __future__ import annotations

import os

import typer
import uvicorn

from cardforge.services.mobile.mobile_launcher import mobile_url

from cardforge.cli.bootstrap import ensure_db

app = typer.Typer(help="Local operator UI commands")


@app.command("serve")
def serve_ui(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind."),
    port: int = typer.Option(8765, "--port", help="Port to bind."),
    mobile: bool = typer.Option(False, "--mobile", help="Serve mobile-first UI and bind to LAN-friendly host."),
    password: str = typer.Option("", "--password", help="Optional UI password. Also enables login protection."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable login protection."),
) -> None:
    """Serve the CardForge local web UI."""
    ensure_db()
    bind_host = "0.0.0.0" if mobile and host == "127.0.0.1" else host
    if mobile:
        os.environ["CARDFORGE_UI_MOBILE_ONLY"] = "true"
        os.environ["CARDFORGE_UI_PUBLIC_BASE_URL"] = mobile_url(host=bind_host, port=port).rsplit("/m", 1)[0]
    if password:
        os.environ["CARDFORGE_UI_PASSWORD"] = password
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "true"
    elif no_auth:
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "false"
    public_path = mobile_url(host=bind_host, port=port) if mobile else f"http://{bind_host}:{port}/"
    typer.echo(f"CardForge UI: {public_path}")
    if mobile:
        typer.echo("Open this URL on your phone/tablet or install it from the browser menu.")
    uvicorn.run("cardforge.web.app:app", host=bind_host, port=port, reload=False)
