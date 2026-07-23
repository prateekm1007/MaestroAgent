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
        """Get the last commit that changed BACKEND code (not worklog/docs-only).

        INFRA-001 fix: the swarm's own worklog commits advance HEAD without
        triggering a backend deploy. A naive live==HEAD check would perpetually
        report drift after any worklog commit. This method finds the last commit
        that actually changed backend code — the commit the backend SHOULD be
        running.
        """
        # Try GitHub API first
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
                # Check if this commit changed backend code
                sha = resp.json().get("sha", "")
                if sha and self._commit_changes_backend(sha):
                    return sha
                # If HEAD doesn't change backend, walk back to find one that does
                return self._find_last_backend_commit(sha)
        except Exception:
            pass

        # Fallback: git log for the last commit that changed backend code
        try:
            # Look for commits that touched src/ or Dockerfile or requirements
            result = subprocess.run(
                ["git", "log", "--format=%H", "-1", "--",
                 "download/MaestroAgent/maestro-personal/src/",
                 "download/MaestroAgent/backend/",
                 "Dockerfile",
                 "download/MaestroAgent/maestro-personal/pyproject.toml"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

        # Ultimate fallback: plain HEAD
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

        return ""

    def _commit_changes_backend(self, sha: str) -> bool:
        """Check if a commit changed backend code (not just worklog/docs)."""
        try:
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
            resp = httpx.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/commits/{sha}",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                files = resp.json().get("files", [])
                for f in files:
                    path = f.get("filename", "")
                    # Backend code paths
                    if any(path.startswith(p) for p in [
                        "download/MaestroAgent/maestro-personal/src/",
                        "download/MaestroAgent/backend/",
                        "Dockerfile",
                        "download/MaestroAgent/maestro-personal/pyproject.toml",
                        ".github/workflows/benchmark.yml",
                    ]):
                        return True
            return False
        except Exception:
            return True  # fail open — assume it changes backend if we can't check

    def _find_last_backend_commit(self, head_sha: str) -> str:
        """Walk back from HEAD to find the last commit that changed backend code."""
        try:
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"
            # Get recent commits
            resp = httpx.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/commits?per_page=20",
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                for commit in resp.json():
                    sha = commit.get("sha", "")
                    if sha and self._commit_changes_backend(sha):
                        return sha
        except Exception:
            pass
        # Fallback: return HEAD if we can't determine
        return head_sha

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

    def trigger_github_actions_deploy(self) -> dict:
        """Trigger the deploy.yml GitHub Actions workflow via the GitHub API.

        This is the FIRST-PARTY deploy path that bypasses the Railway GitHub
        App entirely. GitHub Actions is already connected to the repo (CI
        workflows run on every push), so it can build the Docker image and
        deploy via `railway up` using RAILWAY_API_TOKEN.

        REQUIRES: GITHUB_TOKEN with repo:write scope (to trigger workflows).
        The deploy.yml workflow itself needs RAILWAY_API_TOKEN + service IDs
        as repo secrets.

        Returns: {status, workflow_run_url or error}
        """
        if not self.github_token:
            return {
                "status": "no_github_token",
                "message": "GITHUB_TOKEN not set — cannot trigger workflow_dispatch",
            }
        try:
            # Trigger the deploy workflow via workflow_dispatch
            resp = httpx.post(
                f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/deploy.yml/dispatches",
                headers={
                    "Authorization": f"Bearer {self.github_token}",
                    "Accept": "application/vnd.github+json",
                },
                json={"ref": "main"},
                timeout=15,
            )
            if resp.status_code == 204:
                return {
                    "status": "triggered",
                    "message": "deploy.yml workflow triggered via workflow_dispatch",
                    "monitor_url": f"https://github.com/{GITHUB_REPO}/actions/workflows/deploy.yml",
                }
            else:
                return {
                    "status": "trigger_failed",
                    "status_code": resp.status_code,
                    "body": resp.text[:200],
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def ensure_deployed(self) -> dict:
        """The full autonomous loop: detect drift → diagnose → deploy → verify.

        Uses the GitHub Actions deploy path (first-party, no Railway GitHub
        App needed). Falls back to Railway API if GitHub Actions unavailable.

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

        # Step 3: Trigger deploy via GitHub Actions (first-party path)
        print(f"[deploy_ops] Triggering GitHub Actions deploy (bypasses Railway GitHub App)...")
        gh_result = self.trigger_github_actions_deploy()

        if gh_result["status"] == "triggered":
            print(f"[deploy_ops] ✓ {gh_result['message']}")
            print(f"[deploy_ops] Monitor: {gh_result['monitor_url']}")

            # Step 4: Poll /api/health until live == HEAD (S0 assertion, bounded)
            head_sha = drift_public["head_sha"]
            print(f"[deploy_ops] Polling /api/health until commit == {head_sha[:7]}...")
            start = time.time()
            while time.time() - start < POLL_TIMEOUT_SECONDS:
                time.sleep(POLL_INTERVAL_SECONDS)
                health = self.get_live_health()
                live_sha = health.get("commit", "")
                elapsed = int(time.time() - start)
                print(f"  [{elapsed}s] live={live_sha[:7]} expected={head_sha[:7]}")
                if live_sha.lower().startswith(head_sha[:7].lower()):
                    return {
                        "status": "deployed_and_verified",
                        "live_sha": live_sha,
                        "head_sha": head_sha,
                        "build_time": health.get("build_time"),
                        "deploy_method": "github_actions",
                        "message": "Deploy successful via GitHub Actions, live == HEAD",
                    }
            return {
                "status": "deploy_timeout",
                "head_sha": head_sha,
                "message": f"Deploy did not converge within {POLL_TIMEOUT_SECONDS}s. Check: {gh_result['monitor_url']}",
            }

        # GitHub Actions trigger failed — fall back to Railway API if available
        if gh_result["status"] == "no_github_token":
            print(f"[deploy_ops] No GITHUB_TOKEN — falling back to Railway API deploy...")
        else:
            print(f"[deploy_ops] GitHub Actions trigger failed: {gh_result}")

        if not self.railway:
            return {
                "status": "cannot_trigger",
                "diagnosis": diagnosis,
                "github_actions_result": gh_result,
                "live_sha": drift_public["live_sha"],
                "head_sha": drift_public["head_sha"],
                "stale_seconds": drift_public["stale_seconds"],
                "action_needed": "Add GITHUB_TOKEN (with repo:write) or RAILWAY_API_TOKEN to enable autonomous deploy",
            }

        # Fallback: Railway API deploy (may reuse cached image if no repo trigger)
        try:
            deploy_id = self.railway.trigger_deploy(RAILWAY_SERVICE_ID, branch="main")
            print(f"[deploy_ops] Railway deploy triggered: {deploy_id}")
        except Exception as e:
            return {
                "status": "trigger_failed",
                "diagnosis": diagnosis,
                "github_actions_result": gh_result,
                "error": str(e),
            }

        # Step 5: Verify health
        time.sleep(5)
        health = self.get_live_health()
        live_sha = health.get("commit", "")
        head_sha = drift_public["head_sha"]

        if live_sha.lower().startswith(head_sha[:7].lower()):
            return {
                "status": "deployed_and_verified",
                "live_sha": live_sha,
                "head_sha": head_sha,
                "build_time": health.get("build_time"),
                "deploy_method": "railway_api",
                "message": "Deploy successful via Railway API, live == HEAD",
            }
        else:
            return {
                "status": "deploy_verified_mismatch",
                "health_commit": live_sha,
                "expected": head_sha,
                "diagnosis": diagnosis,
                "message": "Deploy triggered but /api/health still shows old commit — Railway may have reused cached image (no repo trigger to pull new code)",
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
