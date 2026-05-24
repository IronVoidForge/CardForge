from __future__ import annotations

import typer

from cardforge.cli.commands import art, auto, batches, cards, db, doctor, exports, imports, jobs, labs, mobile, prompts, projects, render, resume, review, rework, sets, templates, ui, launchers, worksheets
from cardforge.cli.commands.integrations import comfy_app, llm_app

app = typer.Typer(help="CardForge local card pipeline")

app.add_typer(db.app, name="db")
app.add_typer(projects.app, name="project")
app.add_typer(sets.app, name="set")
app.add_typer(cards.app, name="card")
app.add_typer(batches.app, name="batch")
app.add_typer(imports.app, name="import")
app.add_typer(worksheets.app, name="worksheet")
app.add_typer(art.app, name="art")
app.add_typer(rework.app, name="rework")
app.add_typer(render.app, name="render")
app.add_typer(review.app, name="review")
app.add_typer(llm_app, name="llm")
app.add_typer(comfy_app, name="comfy")
app.add_typer(exports.app, name="export")
app.add_typer(jobs.app, name="job")
app.add_typer(resume.app, name="resume")
app.add_typer(doctor.app, name="doctor")
app.add_typer(prompts.app, name="prompt")
app.add_typer(templates.app, name="template")
app.add_typer(auto.app, name="auto")
app.add_typer(labs.app, name="lab")
app.add_typer(ui.app, name="ui")
app.add_typer(mobile.app, name="mobile")
app.add_typer(launchers.app, name="launcher")


if __name__ == "__main__":
    app()
