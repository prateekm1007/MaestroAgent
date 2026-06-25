"""maestro_cli — the `maestro` command-line tool.

Subcommands:
    maestro serve      Start the FastAPI server
    maestro run        Run a workflow from a template
    maestro resume     Resume a paused/crashed run
    maestro list       List runs / templates / providers
    maestro cost       Show cost breakdown for a run
    maestro config     Get/set config values
    maestro doctor     Check environment health
    maestro --version  Print version
"""

from maestro_cli.main import app

__all__ = ["app"]
