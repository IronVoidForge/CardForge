from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn

from cardforge.cli.bootstrap import ensure_db
from cardforge.services.mobile.mobile_launcher import mobile_url, write_mobile_launcher

app = typer.Typer(help="Mobile-first CardForge UI helpers")


@app.command("serve")
def serve_mobile_ui(
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind. Use 0.0.0.0 for LAN/mobile access."),
    port: int = typer.Option(8765, "--port", help="Port to bind."),
    password: str = typer.Option("", "--password", help="Optional UI password. Also enables login protection."),
    no_auth: bool = typer.Option(False, "--no-auth", help="Disable login protection. Only use on a trusted dev machine."),
) -> None:
    """Serve the mobile-first UI for phones/tablets on the local network."""
    ensure_db()
    if password:
        os.environ["CARDFORGE_UI_PASSWORD"] = password
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "true"
    elif not no_auth:
        os.environ.setdefault("CARDFORGE_UI_REQUIRE_AUTH", "true")
    else:
        os.environ["CARDFORGE_UI_REQUIRE_AUTH"] = "false"
    os.environ["CARDFORGE_UI_MOBILE_ONLY"] = "true"
    public_url = mobile_url(host=host, port=port)
    os.environ["CARDFORGE_UI_PUBLIC_BASE_URL"] = public_url.rsplit("/m", 1)[0]
    typer.echo(f"CardForge Mobile UI: {public_url}")
    typer.echo("Install it from your phone browser's Share/Add to Home Screen menu for app-like use.")
    if not password and not no_auth:
        typer.echo("Warning: auth is required but no --password was supplied. Set CARDFORGE_UI_PASSWORD.")
    uvicorn.run("cardforge.web.app:app", host=host, port=port, reload=False)


@app.command("launcher")
def create_mobile_launcher(
    url: str = typer.Option("", "--url", help="Full mobile URL. Defaults to a guessed LAN URL."),
    host: str = typer.Option("", "--host", help="LAN host/IP to use when --url is omitted."),
    port: int = typer.Option(8765, "--port", help="Port to use when --url is omitted."),
    output: Path | None = typer.Option(None, "--output", help="Output HTML launcher path."),
) -> None:
    """Write a click/tap launcher HTML file that opens CardForge Mobile."""
    ensure_db()
    target_url = url or mobile_url(host=host or None, port=port)
    result = write_mobile_launcher(target_url, output=output)
    typer.echo(f"Wrote mobile launcher: {result.path}")
    typer.echo(f"Launcher target: {result.url}")
