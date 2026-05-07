from __future__ import annotations

from pathlib import Path

import typer

from cardforge.cli.bootstrap import echo_json, ensure_db
from cardforge.services.launchers.operator_launchers import write_operator_launchers

app = typer.Typer(help="Write one-click desktop/mobile launcher files")


@app.command("write")
def write_launchers(
    host: str = typer.Option("", "--host", help="LAN host/IP to place in the mobile launcher HTML."),
    port: int = typer.Option(8765, "--port", help="UI port."),
    output_dir: Path | None = typer.Option(None, "--output-dir", help="Launcher output directory."),
) -> None:
    """Write starter .bat/.sh files plus a mobile HTML opener."""
    ensure_db()
    bundle = write_operator_launchers(host=host or None, port=port, output_dir=output_dir)
    echo_json(
        {
            "directory": str(bundle.directory),
            "mobile_url": bundle.mobile_url,
            "files": [str(path) for path in bundle.files],
        }
    )
