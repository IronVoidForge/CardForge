from __future__ import annotations

import typer

from cardforge.cli.commands import art, auto, batches, cards, db, exports, prompts, projects, render, review, rework, sets, ui
from cardforge.cli.commands.integrations import comfy_app, llm_app

app = typer.Typer(help="CardForge local card pipeline")

app.add_typer(db.app, name="db")
app.add_typer(projects.app, name="project")
app.add_typer(sets.app, name="set")
app.add_typer(cards.app, name="card")
app.add_typer(batches.app, name="batch")
app.add_typer(art.app, name="art")
app.add_typer(rework.app, name="rework")
app.add_typer(render.app, name="render")
app.add_typer(review.app, name="review")
app.add_typer(llm_app, name="llm")
app.add_typer(comfy_app, name="comfy")
app.add_typer(exports.app, name="export")
app.add_typer(prompts.app, name="prompt")
app.add_typer(auto.app, name="auto")
app.add_typer(ui.app, name="ui")


if __name__ == "__main__":
    app()
