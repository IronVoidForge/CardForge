from __future__ import annotations

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.observability.diagnostics_service import DiagnosticsService

app = typer.Typer(help="Local diagnostics")


@app.command("check")
def doctor_check() -> None:
    ensure_db()
    echo_json(DiagnosticsService().check())
