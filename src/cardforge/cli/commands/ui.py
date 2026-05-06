from __future__ import annotations

import typer
import uvicorn

from cardforge.cli.bootstrap import ensure_db

app = typer.Typer(help="Local operator UI commands")


@app.command("serve")
def serve_ui(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind."),
    port: int = typer.Option(8765, "--port", help="Port to bind."),
) -> None:
    """Serve the CardForge local web UI."""
    ensure_db()
    typer.echo(f"CardForge UI: http://{host}:{port}/")
    uvicorn.run("cardforge.web.app:app", host=host, port=port, reload=False)
