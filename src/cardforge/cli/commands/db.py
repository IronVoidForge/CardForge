from __future__ import annotations

import typer

from cardforge.db.schema import migrate, reset
from cardforge.db.session import Database

app = typer.Typer(help="Database commands")


@app.command("init")
def db_init() -> None:
    db = Database()
    with db.connection() as conn:
        migrate(conn)
    typer.echo(f"Database initialized: {db.path}")


@app.command("reset")
def db_reset(yes: bool = typer.Option(False, "--yes", help="Confirm destructive reset.")) -> None:
    if not yes:
        raise typer.BadParameter("Pass --yes to reset the database.")
    db = Database()
    with db.connection() as conn:
        reset(conn)
    typer.echo(f"Database reset: {db.path}")
