"""Status dashboard — a browser-friendly HTML page at /status for quick verification.

This is NOT the PWA — it's a lightweight static HTML page that shows
backend health, provider status, and quick links. Useful for:
- Verifying the backend is up after `./install.sh`
- Checking which LLM providers are reachable
- Quick debugging without opening the full PWA
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from maestro_api.security.policy import set_router_policy, AuthPolicy
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/status", response_class=HTMLResponse)
async def status_page(request: Request) -> HTMLResponse:
    """Lightweight HTML status dashboard."""
    state = request.app.state.maestro
    health = {}
    if state.llm:
        try:
            health = await state.llm.health_check_all()
        except Exception:
            health = {}
    providers = state.llm.available_providers() if state.llm else []
    default_provider = state.llm.default_provider if state.llm else "?"
    default_model = state.llm.default_model if state.llm else "?"
    verifiers = state.verifiers.names() if state.verifiers else []
    plugins = state.plugins.list() if state.plugins else []
    templates = []
    try:
        from pathlib import Path
        tdir = Path(__file__).parent.parent.parent / "examples" / "templates"
        if tdir.exists():
            templates = [p.stem for p in tdir.glob("*.py") if not p.name.startswith("_")]
    except Exception:
        pass

    auth_enabled = getattr(state, "auth_config", None) and state.auth_config.enabled

    provider_rows = ""
    for p in providers:
        ok = health.get(p, False)
        status_badge = "✅ online" if ok else "❌ offline"
        provider_rows += f"<tr><td>{p}</td><td>{status_badge}</td></tr>"

    template_items = "".join(f"<li>{t}</li>" for t in templates) or "<li>(none)</li>"
    verifier_items = "".join(f"<li>{v}</li>" for v in verifiers) or "<li>(none)</li>"
    plugin_items = "".join(f"<li>{pl}</li>" for pl in plugins) or "<li>(none)</li>"

    return HTMLResponse(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MaestroAgent Status</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0a0a0f; color: #f4f4f5; margin: 0; padding: 2rem; line-height: 1.6;
  }}
  .container {{ max-width: 800px; margin: 0 auto; }}
  h1 {{ color: #8b5cf6; margin-bottom: 0.25rem; }}
  .subtitle {{ color: #71717a; margin-bottom: 2rem; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }}
  .card {{ background: #12121a; border: 1px solid #22222e; border-radius: 8px; padding: 1.25rem; }}
  .card h2 {{ font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: #71717a; margin: 0 0 0.75rem 0; }}
  .card .value {{ font-size: 1.5rem; font-family: monospace; color: #22c55e; }}
  .card .value.warn {{ color: #f59e0b; }}
  .card .value.err {{ color: #ef4444; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  td, th {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid #22222e; }}
  th {{ color: #71717a; font-weight: 500; text-transform: uppercase; font-size: 0.75rem; }}
  ul {{ margin: 0; padding-left: 1.25rem; font-size: 0.875rem; color: #a1a1aa; }}
  li {{ margin-bottom: 0.25rem; font-family: monospace; }}
  .links {{ margin-top: 2rem; }}
  .links a {{
    display: inline-block; margin-right: 1rem; padding: 0.5rem 1rem;
    background: #7c3aed; color: white; text-decoration: none; border-radius: 6px;
    font-size: 0.875rem;
  }}
  .links a:hover {{ background: #6d28d9; }}
  .badge {{
    display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px;
    font-size: 0.75rem; font-weight: 600;
  }}
  .badge-on {{ background: #22c55e20; color: #22c55e; }}
  .badge-off {{ background: #ef444420; color: #ef4444; }}
  .footer {{ margin-top: 2rem; color: #71717a; font-size: 0.75rem; }}
</style>
</head>
<body>
<div class="container">
  <h1>MaestroAgent</h1>
  <p class="subtitle">Backend status dashboard · v1.0.0</p>

  <div class="grid">
    <div class="card">
      <h2>Engine</h2>
      <div class="value">✅ Running</div>
    </div>
    <div class="card">
      <h2>Auth</h2>
      <div class="value {'warn' if auth_enabled else ''}">{'🔒 Enabled' if auth_enabled else '🔓 Disabled'}</div>
    </div>
    <div class="card">
      <h2>Default Provider</h2>
      <div class="value">{default_provider} / {default_model}</div>
    </div>
    <div class="card">
      <h2>Providers Online</h2>
      <div class="value">{sum(1 for v in health.values() if v)}/{len(providers)}</div>
    </div>
  </div>

  <div class="card" style="margin-bottom: 1.5rem;">
    <h2>LLM Providers</h2>
    <table>
      <thead><tr><th>Provider</th><th>Status</th></tr></thead>
      <tbody>{provider_rows or '<tr><td colspan="2">No providers configured</td></tr>'}</tbody>
    </table>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Templates ({len(templates)})</h2>
      <ul>{template_items}</ul>
    </div>
    <div class="card">
      <h2>Verifiers ({len(verifiers)})</h2>
      <ul>{verifier_items}</ul>
    </div>
  </div>

  <div class="card" style="margin-bottom: 1.5rem;">
    <h2>Plugins ({len(plugins)})</h2>
    <ul>{plugin_items}</ul>
  </div>

  <div class="links">
    <a href="/">Open PWA →</a>
    <a href="/docs">API Docs →</a>
    <a href="/api/health">Health JSON →</a>
    <a href="/api/doctor">Doctor →</a>
  </div>

  <p class="footer">
    MaestroAgent v1.0.0 · MIT License ·
    <a href="https://github.com/your-org/maestroagent" style="color: #8b5cf6;">GitHub</a>
  </p>
</div>
</body>
</html>
""")

set_router_policy(router, AuthPolicy.PUBLIC)
