#!/usr/bin/env python3
"""Deploy Operations — the agent's autonomous deploy module.

The strategic shift: the agent operates deploys, the founder never touches
a dashboard. This module detects drift, diagnoses stalls, triggers deploys,
and verifies health — autonomously.

REQUIRES:
  - RAILWAY_API_TOKEN env var (Railway team/account token with project access)
  - GITHUB_TOKEN env var (for HEAD SHA — falls back to git rev-parse)

USAGE:
    from deploy_ops import DeployOps
    ops = DeployOps()
    result = ops.ensure_deployed()
    print(result)
    # {"status": "deployed_and_verified", "live_sha": "a9f047f", ...}
    # {"status": "drift_detected", "diagnosis": "...", "action": "triggered_deploy"}
    # {"status": "build_failed", "diagnosis": "...", "logs": "..."}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

# ── Configuration ───────────────────────────────────────────────────────────

RAILWAY_GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"
BACKEND_HEALTH_URL = "https://maestroagent-production.up.railway.app/api/health"
RAILWAY_PROJECT_ID = "4aab2a0c-349d-452a-ae9a-5c5f0205817f"
# NOTE: The service ID in railway.json (0ad2810b) is STALE. The actual Railway
# service ID for the backend is c12adfcf (discovered via GraphQL introspection).
RAILWAY_SERVICE_ID = "c12adfcf-524d-4b99-8837-9c495065bb5c"
RAILWAY_ENVIRONMENT_ID = "38916bb1-5f30-47dc-91eb-9baf56e99591"  # production
GITHUB_REPO = "prateekm1007/MaestroAgent"
GITHUB_REPO_ID = "1282275626"  # Railway's internal ID for the connected repo

# Drift thresholds
STALE_THRESHOLD_SECONDS = 900  # 15 min — if older than this + drifted, auto-deploy
POLL_INTERVAL_SECONDS = 15
POLL_TIMEOUT_SECONDS = 900  # 15 min max wait for deploy


@dataclass
class DriftReport:
    live_sha: str
    head_sha: str
    drifted: bool
    stale_seconds: int
    deploy_status: str  # SUCCESS / FAILED / BUILDING / QUEUED / null
    deploy_created_at: str | None
    deploy_id: str | None


class RailwayGraphQLClient:
    """Thin client for Railway's GraphQL API."""

    def __init__(self, token: str):
        self.headers = {"Authorization": f"Bearer {token}"}

    def _post(self, query: str, variables: dict) -> dict:
        resp = httpx.post(
            RAILWAY_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=self.headers,
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Railway API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if data.get("errors"):
            raise RuntimeError(f"Railway GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def get_active_deployment(self, service_id: str) -> dict:
        """Get the most recent deployment for a service.

        Uses the v2 schema: project.services (plural), meta is a scalar JSON.
        """
        query = """
        query($projectId: String!) {
          project(id: $projectId) {
            services(first: 10) {
              edges {
                node {
                  id
                  name
                  deployments(first: 1) {
                    edges {
                      node {
                        id
                        status
                        createdAt
                        statusUpdatedAt
                        meta
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._post(query, {"projectId": RAILWAY_PROJECT_ID})
        services = data.get("project", {}).get("services", {}).get("edges", [])
        for svc in services:
            if svc["node"]["id"] == service_id:
                deps = svc["node"]["deployments"]["edges"]
                if deps:
                    return deps[0]["node"]
        return {}

    def get_service_settings(self, service_id: str) -> dict:
        """Get service settings including auto-deploy status."""
        query = """
        query($projectId: String!, $serviceId: String!) {
          project(id: $projectId) {
            service(id: $serviceId) {
              settings
            }
          }
        }
        """
        data = self._post(query, {
            "projectId": RAILWAY_PROJECT_ID,
            "serviceId": service_id,
        })
        return data.get("project", {}).get("service", {}).get("settings", {})

    def trigger_deploy(self, service_id: str, branch: str = "main") -> str:
        """Trigger a manual deploy via serviceInstanceDeploy with latestCommit.

        Uses the v2 mutation: serviceInstanceDeploy(environmentId, serviceId,
        latestCommit, commitSha). Returns the deployment ID if available.

        NOTE: If the service has no GitHub repo trigger connected (the repo
        trigger is what tells Railway to pull code from GitHub), this will
        return true but NOT actually rebuild — Railway reuses the cached
        image. See diagnose_repo_trigger() for the root cause.
        """
        mutation = """
        mutation($environmentId: String!, $serviceId: String!, $latestCommit: Boolean!) {
          serviceInstanceDeploy(environmentId: $environmentId, serviceId: $serviceId, latestCommit: $latestCommit)
        }
        """
        self._post(mutation, {
            "environmentId": RAILWAY_ENVIRONMENT_ID,
            "serviceId": service_id,
            "latestCommit": True,
        })
        return "triggered"

    def get_build_logs(self, service_id: str, deployment_id: str | None = None) -> str:
        """Get build logs for a deployment.

        NOTE: Railway v2 schema doesn't expose buildLogs as a field on
        Deployment. Logs are available via the Railway CLI or dashboard.
        This returns a placeholder pointing to where to find logs.
        """
        return f"Logs not available via GraphQL v2. Check Railway dashboard or CLI: railway logs --deployment {deployment_id}"

    def get_repo_triggers(self, service_id: str) -> list:
        """Get repo triggers for a service. Empty list = no GitHub connection."""
        query = """
        query($projectId: String!) {
          project(id: $projectId) {
            services(first: 10) {
              edges {
                node {
                  id
                  name
                  repoTriggers {
                    edges {
                      node {
                        id
                        branch
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._post(query, {"projectId": RAILWAY_PROJECT_ID})
        services = data.get("project", {}).get("services", {}).get("edges", [])
        for svc in services:
            if svc["node"]["id"] == service_id:
                return svc["node"]["repoTriggers"]["edges"]
        return []

    def create_repo_trigger(self, service_id: str, branch: str = "main") -> dict:
        """Create a deployment trigger connecting the service to the GitHub repo.

        This is what wires up auto-deploy: once the trigger exists, every push
        to the branch triggers a rebuild.

        REQUIRES: The Railway GitHub app must be installed on the repo with
        repo access. If not, this returns an error:
        'Cannot create deployment trigger because no one in the project has
        access to it'

        Fix: Go to railway.com → Settings → GitHub → ensure the Railway app
        is installed on prateekm1007/MaestroAgent with repo access.
        """
        mutation = """
        mutation($input: DeploymentTriggerCreateInput!) {
          deploymentTriggerCreate(input: $input) {
            id
            branch
          }
        }
        """
        try:
            data = self._post(mutation, {
                "input": {
                    "branch": branch,
                    "environmentId": RAILWAY_ENVIRONMENT_ID,
                    "projectId": RAILWAY_PROJECT_ID,
                    "provider": "github",
                    "repository": GITHUB_REPO_ID,
                    "serviceId": service_id,
                }
            })
            return {"status": "created", "trigger": data.get("deploymentTriggerCreate", {})}
        except RuntimeError as e:
            if "no one in the project has access" in str(e):
                return {
                    "status": "github_app_not_authorized",
                    "error": str(e),
                    "fix": "Go to railway.com → Settings → GitHub → install/authorize the Railway GitHub app on prateekm1007/MaestroAgent with repo access. This is a one-time browser-based OAuth step that cannot be done via API.",
                }
            return {"status": "error", "error": str(e)}


class DeployOps:
    """The agent operates deploys. The founder never touches a dashboard."""

    def __init__(self, railway_token: str | None = None):
        self.railway_token = railway_token or os.environ.get("RAILWAY_API_TOKEN")
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.railway = RailwayGraphQLClient(self.railway_token) if self.railway_token else None

    # ── Drift detection (works WITHOUT Railway token — uses public endpoints) ──

    def get_head_sha(self) -> str:
        """Get HEAD SHA via GitHub API (public, no token needed for public repos)
        or git rev-parse as fallback."""
        # Try GitHub API first (works in CI)
        try:
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
            resp = httpx.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/commits/main",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("sha", "")
        except Exception:
            pass

        # Fallback: git rev-parse (works locally)
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return ""

    def get_live_health(self) -> dict:
        """Fresh fetch of backend /api/health (live-claim rule: always fresh)."""
        resp = httpx.get(BACKEND_HEALTH_URL, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def check_drift_public(self) -> dict:
        """Detect drift using PUBLIC endpoints only (no Railway token needed).

        This is the drift-detection half — it works right now, without any
        secrets. The deploy-trigger half needs RAILWAY_API_TOKEN.
        """
        head_sha = self.get_head_sha()
        health = self.get_live_health()
        live_sha = health.get("commit", "")
        build_time = health.get("build_time", "")

        # Compute stale duration from build_time
        stale_seconds = 0
        if build_time:
            try:
                bt = datetime.fromisoformat(build_time.replace("Z", "+00:00"))
                stale_seconds = int((datetime.now(timezone.utc) - bt).total_seconds())
            except Exception:
                pass

        drifted = bool(live_sha) and bool(head_sha) and not live_sha.lower().startswith(head_sha[:7].lower())

        return {
            "live_sha": live_sha,
            "head_sha": head_sha,
            "drifted": drifted,
            "stale_seconds": stale_seconds,
            "build_time": build_time,
            "health_status": health.get("status"),
            "router_loaded": health.get("router_loaded"),  # may be None if not in health
        }

    # ── Full drift detection (needs Railway token for deploy_status) ──────────

    def check_drift(self) -> DriftReport:
        """Full drift detection including Railway deploy status. Needs token."""
        if not self.railway:
            raise RuntimeError("RAILWAY_API_TOKEN not set — cannot query Railway API")

        head_sha = self.get_head_sha()
        deploy = self.railway.get_active_deployment(RAILWAY_SERVICE_ID)
        live_sha = deploy.get("meta", {}).get("commitSha", "")
        deploy_status = deploy.get("status", "")
        deploy_created_at = deploy.get("createdAt", "")
        deploy_id = deploy.get("id", "")

        stale_seconds = 0
        if deploy_created_at:
            try:
                ct = datetime.fromisoformat(deploy_created_at.replace("Z", "+00:00"))
                stale_seconds = int((datetime.now(timezone.utc) - ct).total_seconds())
            except Exception:
                pass

        drifted = bool(live_sha) and bool(head_sha) and not live_sha.lower().startswith(head_sha[:7].lower())

        return DriftReport(
            live_sha=live_sha,
            head_sha=head_sha,
            drifted=drifted,
            stale_seconds=stale_seconds,
            deploy_status=deploy_status,
            deploy_created_at=deploy_created_at,
            deploy_id=deploy_id,
        )

    def diagnose_stall(self) -> str:
        """Diagnose why the backend hasn't deployed. Returns a diagnosis string."""
        if not self.railway:
            # Public-only diagnosis
            drift = self.check_drift_public()
            if drift["drifted"] and drift["stale_seconds"] > STALE_THRESHOLD_SECONDS:
                return (
                    f"DRIFTED: live={drift['live_sha'][:7]} vs head={drift['head_sha'][:7]}, "
                    f"stale {drift['stale_seconds']}s ({drift['stale_seconds']//3600}h{(drift['stale_seconds']%3600)//60}m). "
                    f"Cannot diagnose further without RAILWAY_API_TOKEN."
                )
            return f"No drift detected (live={drift['live_sha'][:7]})"

        # Use public drift detection for the commit comparison (health endpoint
        # is the source of truth for the live commit, not Railway's meta)
        drift_public = self.check_drift_public()

        if not drift_public["drifted"]:
            return f"No drift (live={drift_public['live_sha'][:7]})"

        # Check for repo triggers — if there are ZERO, Railway can't pull code
        triggers = self.railway.get_repo_triggers(RAILWAY_SERVICE_ID)
        if not triggers:
            # Try to create a repo trigger
            trigger_result = self.railway.create_repo_trigger(RAILWAY_SERVICE_ID)
            if trigger_result.get("status") == "github_app_not_authorized":
                return (
                    f"ROOT CAUSE: backend service has ZERO repo triggers — Railway cannot "
                    f"pull new code from GitHub. Attempted to create trigger but failed: "
                    f"Railway GitHub app is not authorized on the repo. "
                    f"FIX: Go to railway.com → Settings → GitHub → install/authorize the "
                    f"Railway GitHub app on prateekm1007/MaestroAgent with repo access. "
                    f"This is a one-time browser-based OAuth step."
                )
            elif trigger_result.get("status") == "created":
                return (
                    f"ROOT CAUSE: backend service had zero repo triggers. "
                    f"Created trigger successfully — auto-deploy should now work. "
                    f"Triggering manual deploy."
                )
            else:
                return f"ROOT CAUSE: no repo triggers. Trigger creation failed: {trigger_result}"

        # Has triggers — check deploy status
        deploy = self.railway.get_active_deployment(RAILWAY_SERVICE_ID)
        deploy_status = deploy.get("status", "")
        stale_seconds = drift_public["stale_seconds"]

        if deploy_status == "FAILED":
            return f"Build failed. {self.railway.get_build_logs(RAILWAY_SERVICE_ID, deploy.get('id'))}"

        if deploy_status in ("BUILDING", "QUEUED", "DEPLOYING"):
            return f"Deploy in progress ({deploy_status})"

        if stale_seconds > STALE_THRESHOLD_SECONDS:
            return (
                f"DRIFTED: live={drift_public['live_sha'][:7]} vs head={drift_public['head_sha'][:7]}, "
                f"stale {stale_seconds}s. Repo trigger exists but no new build. "
                f"Triggering manual deploy."
            )

        return f"Drifted but recent ({stale_seconds}s) — deploy may be in flight"

    # ── Autonomous deploy loop ────────────────────────────────────────────────

    def ensure_deployed(self) -> dict:
        """The full autonomous loop: detect drift → diagnose → deploy → verify.

        Returns a result dict with status and details. No human intervention.
        """
        # Step 1: Check drift (public endpoints, no token needed)
        drift_public = self.check_drift_public()
        if not drift_public["drifted"]:
            return {
                "status": "already_current",
                "live_sha": drift_public["live_sha"],
                "head_sha": drift_public["head_sha"],
                "message": "Live == HEAD, no action needed",
            }

        # Step 2: Diagnose
        diagnosis = self.diagnose_stall()
        print(f"[deploy_ops] Drift detected: {diagnosis}")

        # Step 3: Trigger deploy (NEEDS RAILWAY_API_TOKEN)
        if not self.railway:
            return {
                "status": "cannot_trigger_without_token",
                "diagnosis": diagnosis,
                "live_sha": drift_public["live_sha"],
                "head_sha": drift_public["head_sha"],
                "stale_seconds": drift_public["stale_seconds"],
                "action_needed": "Add RAILWAY_API_TOKEN to environment so deploy_ops can trigger deploys autonomously",
            }

        # Check for build failure — don't redeploy if the build is broken
        if "Build failed" in diagnosis:
            return {
                "status": "build_failed",
                "diagnosis": diagnosis,
                "action": "escalate_to_coder — fix the build error before redeploying",
            }

        # Trigger manual deploy
        try:
            deploy_id = self.railway.trigger_deploy(RAILWAY_SERVICE_ID, branch="main")
            print(f"[deploy_ops] Deploy triggered: {deploy_id}")
        except Exception as e:
            return {
                "status": "trigger_failed",
                "diagnosis": diagnosis,
                "error": str(e),
            }

        # Step 4: Poll until complete (bounded timeout)
        print(f"[deploy_ops] Polling deploy status every {POLL_INTERVAL_SECONDS}s (max {POLL_TIMEOUT_SECONDS}s)...")
        start = time.time()
        while time.time() - start < POLL_TIMEOUT_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            deploy = self.railway.get_active_deployment(RAILWAY_SERVICE_ID)
            status = deploy.get("status", "")
            print(f"  [{int(time.time()-start)}s] status={status}")
            if status == "SUCCESS":
                break
            if status == "FAILED":
                logs = self.railway.get_build_logs(RAILWAY_SERVICE_ID, deploy.get("id"))
                return {
                    "status": "deploy_failed",
                    "diagnosis": diagnosis,
                    "logs": logs[:500],
                }
        else:
            return {
                "status": "deploy_timeout",
                "deploy_id": deploy_id,
                "message": f"Deploy did not complete within {POLL_TIMEOUT_SECONDS}s",
            }

        # Step 5: Verify health (fresh fetch, live-claim rule)
        time.sleep(5)  # give the new deployment a moment to start serving
        health = self.get_live_health()
        live_sha = health.get("commit", "")
        head_sha = drift_public["head_sha"]

        if live_sha.lower().startswith(head_sha[:7].lower()):
            return {
                "status": "deployed_and_verified",
                "live_sha": live_sha,
                "head_sha": head_sha,
                "build_time": health.get("build_time"),
                "message": "Deploy successful, live == HEAD",
            }
        else:
            return {
                "status": "deploy_verified_mismatch",
                "health_commit": live_sha,
                "expected": head_sha,
                "message": "Deploy reported SUCCESS but /api/health still shows old commit — possible edge-cache or deploy-swap delay",
            }


def main():
    """CLI entry point — run ensure_deployed() and print the result."""
    print("=" * 72)
    print("DEPLOY OPS — Autonomous deploy detection and remediation")
    print("=" * 72)

    ops = DeployOps()

    # Always start with public drift detection (works without token)
    print("\n[1] Public drift detection (no token needed):")
    drift = ops.check_drift_public()
    print(f"  HEAD SHA:       {drift['head_sha'][:7]}")
    print(f"  Live SHA:       {drift['live_sha'][:7]}")
    print(f"  Drifted:        {drift['drifted']}")
    print(f"  Stale:          {drift['stale_seconds']}s ({drift['stale_seconds']//3600}h{(drift['stale_seconds']%3600)//60}m)")
    print(f"  Build time:     {drift['build_time']}")

    if not drift["drifted"]:
        print("\n✓ No drift — live == HEAD")
        return 0

    print(f"\n[2] Drift detected. Running ensure_deployed()...")
    result = ops.ensure_deployed()

    print(f"\n[3] Result:")
    print(json.dumps(result, indent=2))

    # Exit code: 0 if deployed/verified, 1 if action needed
    if result["status"] in ("already_current", "deployed_and_verified"):
        print("\n✓ Deploy verified")
        return 0
    else:
        print(f"\n✗ Action needed: {result['status']}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
