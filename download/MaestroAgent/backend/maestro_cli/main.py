"""`maestro` CLI entrypoint — Typer-based."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="maestro",
    help="MaestroAgent — the ultimate conductor for AI agents.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Print version."""
    from maestro_core import __version__
    rprint(f"maestro {__version__}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8765, help="Bind port"),
    db_path: str = typer.Option("maestro.db", help="SQLite path"),
    chroma_path: str = typer.Option(".maestro/chroma", help="Chroma path"),
    reload: bool = typer.Option(False, help="Auto-reload (dev)"),
) -> None:
    """Start the FastAPI server."""
    import uvicorn
    from maestro_api.main import create_app

    api_app = create_app(db_path=db_path, chroma_path=chroma_path)
    rprint(f"[bold green]MaestroAgent[/] starting on http://{host}:{port}")
    rprint(f"  DB:     {db_path}")
    rprint(f"  Chroma: {chroma_path}")
    uvicorn.run(api_app, host=host, port=port, reload=reload)


@app.command()
def run(
    template_path: str = typer.Argument(..., help="Path to a template .py file"),
    goal: str = typer.Option(..., "--goal", "-g", help="Run goal"),
    max_cost: float = typer.Option(10.0, help="Max cost in USD"),
    max_iterations: int = typer.Option(100, help="Max iterations"),
    provider: str | None = typer.Option(None, help="LLM provider"),
    model: str | None = typer.Option(None, help="LLM model"),
    watch: bool = typer.Option(True, help="Stream events to console"),
) -> None:
    """Run a workflow from a template file."""
    asyncio.run(_run_template(template_path, goal, max_cost, max_iterations, provider, model, watch))


@app.command()
def resume(run_id: str) -> None:
    """Resume a paused/crashed run."""
    rprint(f"[yellow]Resume not yet implemented in CLI.[/] Use the desktop UI or POST /api/runs/{run_id}/resume")


@app.command(name="list")
def list_(
    what: str = typer.Argument("templates", help="What to list: templates|providers|runs"),
) -> None:
    """List templates, providers, or runs."""
    if what == "templates":
        _list_templates()
    elif what == "providers":
        _list_providers()
    elif what == "runs":
        rprint("[yellow]Run listing requires a running server.[/]")
    else:
        rprint(f"[red]Unknown list target: {what}[/]")


@app.command()
def cost(run_id: str, db_path: str = typer.Option("maestro.db", help="SQLite path")) -> None:
    """Show cost breakdown for a run."""
    from maestro_llm.cost import CostLedger
    ledger = CostLedger(db_path=db_path)
    total = asyncio.run(ledger.total_for_run(run_id))
    breakdown = asyncio.run(ledger.breakdown_for_run(run_id))
    rprint(f"[bold]Run {run_id}[/]: ${total:.4f} total")
    table = Table("Provider", "Model", "Prompt tok", "Completion tok", "Cost USD", "Calls")
    for b in breakdown:
        table.add_row(
            b["provider"], b["model"],
            str(b["prompt_tokens"]), str(b["completion_tokens"]),
            f"${b['cost_usd']:.4f}", str(b["calls"]),
        )
    console.print(table)


@app.command()
def config(
    action: str = typer.Argument(..., help="get|set|list"),
    key: str = typer.Argument(None),  # type: ignore
    value: str = typer.Argument(None),  # type: ignore
) -> None:
    """Get/set config values (stored in ~/.maestro/config.json)."""
    config_path = Path.home() / ".maestro" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    cfg: dict[str, Any] = {}
    if config_path.exists():
        cfg = json.loads(config_path.read_text())
    if action == "list":
        rprint(json.dumps(cfg, indent=2))
    elif action == "get":
        if not key:
            rprint("[red]get requires a key[/]")
            raise typer.Exit(1)
        rprint(cfg.get(key, ""))
    elif action == "set":
        if not key or value is None:
            rprint("[red]set requires key and value[/]")
            raise typer.Exit(1)
        # Try parsing as JSON; fall back to string.
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        cfg[key] = parsed
        config_path.write_text(json.dumps(cfg, indent=2))
        rprint(f"[green]Set {key} = {parsed}[/]")
    else:
        rprint(f"[red]Unknown config action: {action}[/]")


@app.command()
def doctor() -> None:
    """Check environment health."""
    rprint("[bold]MaestroAgent doctor[/]\n")
    # Python version
    rprint(f"  Python: [green]{sys.version.split()[0]}[/]")
    # Optional deps
    for mod, label in [
        ("fastapi", "FastAPI"),
        ("langgraph", "LangGraph"),
        ("crewai", "CrewAI"),
        ("chromadb", "ChromaDB"),
        ("networkx", "NetworkX"),
        ("httpx", "httpx"),
        ("keyring", "keyring"),
    ]:
        try:
            __import__(mod)
            rprint(f"  {label}: [green]ok[/]")
        except ImportError:
            rprint(f"  {label}: [red]missing[/]")
    # Ollama
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
            rprint(f"  Ollama: [green]ok[/] ({len(models)} models)")
            for m in models[:5]:
                rprint(f"    - {m}")
        else:
            rprint(f"  Ollama: [yellow]not running[/]")
    except Exception:
        rprint(f"  Ollama: [yellow]not running[/]")
    # Docker
    try:
        import subprocess
        r = subprocess.run(["docker", "--version"], capture_output=True, timeout=3.0)
        if r.returncode == 0:
            rprint(f"  Docker: [green]ok[/] ({r.stdout.decode().strip()})")
        else:
            rprint(f"  Docker: [yellow]not installed[/]")
    except Exception:
        rprint(f"  Docker: [yellow]not installed[/]")
    # API keys
    for var in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY"]:
        if os.environ.get(var):
            rprint(f"  {var}: [green]set[/]")
        else:
            rprint(f"  {var}: [dim]not set[/]")


async def _run_template(
    template_path: str,
    goal: str,
    max_cost: float,
    max_iterations: int,
    provider: str | None,
    model: str | None,
    watch: bool,
) -> None:
    """Load a template, build a graph, run it, optionally stream events."""
    import importlib.util
    import uuid
    from maestro_core.context import RunConfig, RunContext
    from maestro_core.engine import OrchestrationEngine
    from maestro_core.checkpoint import SQLiteCheckpointStore
    from maestro_core.streaming import EventBus, EventType
    from maestro_llm.router import LLMRouter
    from maestro_memory.manager import MemoryManager
    from maestro_memory.short_term import ShortTermMemory
    from maestro_memory.vector import InMemoryVectorMemory
    from maestro_memory.graph import NetworkXGraphMemory
    from maestro_memory.long_term import LongTermMemory
    from maestro_verify.registry import VerifierRegistry
    from maestro_plugins.registry import PluginRegistry

    # Load template.
    path = Path(template_path)
    if not path.exists():
        rprint(f"[red]Template not found: {path}[/]")
        raise typer.Exit(1)
    spec = importlib.util.spec_from_file_location("template", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build_graph"):
        rprint(f"[red]Template has no build_graph() function[/]")
        raise typer.Exit(1)
    graph = module.build_graph(goal=goal)

    # Build context.
    run_id = str(uuid.uuid4())
    db_path = "maestro.db"
    ledger = None
    try:
        from maestro_llm.cost import CostLedger
        ledger = CostLedger(db_path=db_path)
    except Exception:
        pass

    llm = LLMRouter.with_defaults(
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        grok_api_key=os.environ.get("XAI_API_KEY"),
        ledger=ledger,
    )
    if provider:
        llm.default_provider = provider
    if model:
        llm.default_model = model

    memory = MemoryManager(
        short_term=ShortTermMemory(),
        semantic=InMemoryVectorMemory(),
        graph=NetworkXGraphMemory(persist_path=".maestro/graph.json"),
        long_term=LongTermMemory(db_path=db_path),
    )
    checkpoints = SQLiteCheckpointStore(db_path=db_path)
    bus = EventBus()
    bus.start()

    if watch:
        async def _print_event(event):
            rprint(f"  [dim]{event.type.value}[/] {json.dumps(event.payload)[:200]}")
        bus.subscribe(_print_event)

    plugins = PluginRegistry()
    plugins.discover()

    config = RunConfig(
        run_id=run_id,
        template=path.stem,
        goal=goal,
        max_cost_usd=max_cost,
        max_iterations=max_iterations,
        default_provider=provider,
        default_model=model,
    )
    ctx = RunContext(
        config=config,
        llm=llm,
        memory=memory,
        checkpoints=checkpoints,
        events=bus,
        verifiers=VerifierRegistry(),
        plugins=plugins,
    )

    rprint(f"[bold green]Starting run[/] {run_id}")
    rprint(f"  Template: {path.stem}")
    rprint(f"  Goal:     {goal}")
    rprint(f"  Budget:   ${max_cost}")
    rprint()

    engine = OrchestrationEngine(ctx=ctx, graph=graph)
    result = await engine.run()
    rprint()
    rprint(f"[bold]Result:[/] status={result.status.value} steps={result.steps_executed} cost=${result.cost_usd:.4f}")
    if result.error:
        rprint(f"[red]Error:[/] {result.error}")
    await bus.stop()


def _list_templates() -> None:
    """List templates from examples/templates/."""
    templates_dir = Path(__file__).parent.parent / "examples" / "templates"
    if not templates_dir.exists():
        rprint("[yellow]No templates directory.[/]")
        return
    table = Table("Name", "Description")
    for p in templates_dir.glob("*.py"):
        if p.name.startswith("_"):
            continue
        text = p.read_text()
        desc = ""
        if '"""' in text:
            start = text.find('"""') + 3
            end = text.find('"""', start)
            if end > start:
                desc = text[start:end].strip().split("\n")[0]
        table.add_row(p.stem, desc)
    console.print(table)


def _list_providers() -> None:
    """List configured providers."""
    from maestro_llm.router import LLMRouter
    r = LLMRouter.with_defaults(
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY"),
        grok_api_key=os.environ.get("XAI_API_KEY"),
    )
    table = Table("Provider", "Default Model", "Available")
    for name in r.available_providers():
        table.add_row(
            name,
            r.default_models.get(name, "?"),
            "[green]yes[/]" if r.providers[name] else "[red]no[/]",
        )
    console.print(table)


if __name__ == "__main__":
    app()
