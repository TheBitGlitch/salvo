from cyclopts import App

from .sub_apps import run_app, manage_app

app = App(
    name="salvo",
    version="2.0.0",
    help_epilogue="Developed by `@TheBitGlitch` • GitHub",
    result_action="return_value",
)

app.command(run_app)
app.command(manage_app())
