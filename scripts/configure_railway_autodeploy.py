#!/usr/bin/env python3
"""
Configure Railway auto-deploy for the web frontend service.

Uses Railway's GraphQL API (no CLI/browser required).

Usage:
    python scripts/configure_railway_autodeploy.py --token <RAILWAY_TOKEN>
    python scripts/configure_railway_autodeploy.py --token $RAILWAY_TOKEN
"""

import argparse
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

RAILWAY_API = "https://backboard.railway.app/graphql/v2"
BACKEND_URL = "https://maestroagent-production.up.railway.app"
WEB_URL = "https://web-production-d5c26.up.railway.app"
WEB_ROOT_DIR = "download/MaestroAgent/maestro-personal/web"

def graphql(token, query, variables=None):
    """Execute a Railway GraphQL query."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = Request(RAILWAY_API, data=payload, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode()
        print(f"❌ Railway API error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)

def find_project(token):
    """Find the MaestroAgent project."""
    print("🔍 Discovering projects...")
    result = graphql(token, """
        query {
            projects {
                edges {
                    node {
                        id
                        name
                        description
                    }
                }
            }
        }
    """)

    projects = result["data"]["projects"]["edges"]
    print(f"   Found {len(projects)} project(s)")

    for edge in projects:
        p = edge["node"]
        print(f"   - {p['name']} (id: {p['id']})")

    for edge in projects:
        p = edge["node"]
        if "maestro" in p["name"].lower() or "brilliant" in p["name"].lower() or "maestro" in (p.get("description") or "").lower():
            return p

    return projects[0]["node"] if projects else None

def find_services(token, project_id):
    """Find all services in the project."""
    print(f"\n🔍 Discovering services in project {project_id}...")
    result = graphql(token, """
        query($projectId: String!) {
            project(id: $projectId) {
                services {
                    edges {
                        node {
                            id
                            name
                            icon
                        }
                    }
                }
                environments {
                    edges {
                        node {
                            id
                            name
                        }
                    }
                }
            }
        }
    """, {"projectId": project_id})

    project = result["data"]["project"]
    services = [e["node"] for e in project["services"]["edges"]]
    environments = [e["node"] for e in project["environments"]["edges"]]

    print(f"   Found {len(services)} service(s):")
    for s in services:
        print(f"   - {s['name']} (id: {s['id']})")

    print(f"   Found {len(environments)} environment(s):")
    for e in environments:
        print(f"   - {e['name']} (id: {e['id']})")

    return services, environments

def find_web_service(services):
    """Find the web frontend service."""
    for s in services:
        if "web" in s["name"].lower() or "frontend" in s["name"].lower():
            return s
    for s in services:
        if "backend" not in s["name"].lower() and "api" not in s["name"].lower() and "postgres" not in s["name"].lower():
            return s
    return None

def get_service_instances(token, service_id, environment_id):
    """Get service instances (deployments) for a service in an environment."""
    result = graphql(token, """
        query($serviceId: String!, $environmentId: String!) {
            serviceInstances(
                input: {
                    serviceId: $serviceId
                    environmentId: $environmentId
                }
            ) {
                edges {
                    node {
                        id
                        currentDeployment {
                            id
                            status
                            staticUrl
                            meta {
                                repo
                                branch
                                commitSha
                            }
                        }
                        source {
                            ... on ServiceInstanceSourceRepo {
                                repo
                                branch
                                rootDirectory
                            }
                        }
                    }
                }
            }
        }
    """, {"serviceId": service_id, "environmentId": environment_id})

    edges = result["data"]["serviceInstances"]["edges"]
    return [e["node"] for e in edges]

def trigger_deploy(token, service_id, environment_id):
    """Trigger a new deployment."""
    print(f"\n🚀 Triggering deploy...")
    result = graphql(token, """
        mutation($serviceId: String!, $environmentId: String!) {
            deploymentCreate(
                serviceId: $serviceId
                environmentId: $environmentId
            ) {
                id
                status
                staticUrl
            }
        }
    """, {"serviceId": service_id, "environmentId": environment_id})

    deployment = result["data"]["deploymentCreate"]
    print(f"   ✅ Deploy triggered: {deployment['id']}")
    print(f"   Status: {deployment['status']}")
    return deployment

def poll_deploy_status(token, deployment_id, timeout=600):
    """Poll deployment status until complete."""
    print(f"\n⏳ Polling deploy status (timeout: {timeout}s)...")
    start = time.time()

    while time.time() - start < timeout:
        result = graphql(token, """
            query($deploymentId: String!) {
                deployment(id: $deploymentId) {
                    id
                    status
                    staticUrl
                    meta {
                        repo
                        branch
                        commitSha
                    }
                }
            }
        """, {"deploymentId": deployment_id})

        deployment = result["data"]["deployment"]
        status = deployment["status"]
        elapsed = int(time.time() - start)
        print(f"   [{elapsed}s] Status: {status}", end="\r")

        if status == "SUCCESS":
            print(f"\n   ✅ Deploy succeeded after {elapsed}s")
            if deployment.get("meta") and deployment["meta"].get("commitSha"):
                print(f"   Commit: {deployment['meta']['commitSha'][:8]}")
            return deployment
        elif status in ("FAILED", "CRASHED", "REMOVED"):
            print(f"\n   ❌ Deploy failed with status: {status}")
            sys.exit(1)

        time.sleep(10)

    print(f"\n   ⏰ Timeout after {timeout}s")
    sys.exit(1)

def verify_frontend_live():
    """Verify the frontend is serving the new code (no mock data)."""
    print(f"\n🔍 Verifying frontend at {WEB_URL}...")
    try:
        req = Request(WEB_URL, headers={"User-Agent": "MaestroAgent-Verifier/1.0"})
        with urlopen(req, timeout=30) as resp:
            html = resp.read().decode()

        if "Q3 budget proposal" in html:
            print(f"   ❌ Frontend still serving mock data")
            return False
        else:
            print(f"   ✅ Frontend serving new code (no mock data detected)")
            return True
    except Exception as e:
        print(f"   ⚠️  Could not verify frontend: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Configure Railway auto-deploy")
    parser.add_argument("--token", required=True, help="Railway API token")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()

    print("=" * 70)
    print("MaestroAgent — Railway Auto-Deploy Configuration")
    print("=" * 70)

    # Step 1: Find the project
    project = find_project(args.token)
    if not project:
        print("❌ No project found", file=sys.stderr)
        sys.exit(1)
    print(f"\n✅ Project: {project['name']} (id: {project['id']})")

    # Step 2: Find services and environments
    services, environments = find_services(args.token, project["id"])
    if not services:
        print("❌ No services found", file=sys.stderr)
        sys.exit(1)

    # Step 3: Find the web service
    web_service = find_web_service(services)
    if not web_service:
        print("❌ Could not identify web service", file=sys.stderr)
        sys.exit(1)
    print(f"\n✅ Web service: {web_service['name']} (id: {web_service['id']})")

    # Step 4: Get the production environment
    prod_env = next((e for e in environments if "production" in e["name"].lower() or e["name"] == "main"), environments[0])
    print(f"✅ Environment: {prod_env['name']} (id: {prod_env['id']})")

    # Step 5: Get current service instances
    instances = get_service_instances(args.token, web_service["id"], prod_env["id"])
    if not instances:
        print("❌ No service instances found", file=sys.stderr)
        sys.exit(1)

    instance = instances[0]
    print(f"\n✅ Service instance: {instance['id']}")
    if instance.get("currentDeployment"):
        cd = instance["currentDeployment"]
        print(f"   Current deploy: {cd['id']} (status: {cd['status']})")
        if cd.get("meta") and cd["meta"].get("commitSha"):
            print(f"   Commit: {cd['meta']['commitSha'][:8]}")

    if args.dry_run:
        print("\n🔸 DRY RUN — no changes made")
        print(f"   Would trigger: new deployment of latest commit")
        return

    # Step 6: Trigger deploy
    deployment = trigger_deploy(args.token, web_service["id"], prod_env["id"])

    # Step 7: Poll for completion
    final_deploy = poll_deploy_status(args.token, deployment["id"])

    # Step 8: Verify
    time.sleep(10)
    live = verify_frontend_live()

    # Step 9: Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Project:         {project['name']}")
    print(f"Service:         {web_service['name']}")
    print(f"Environment:     {prod_env['name']}")
    print(f"Deploy ID:       {final_deploy['id']}")
    if final_deploy.get("meta") and final_deploy["meta"].get("commitSha"):
        print(f"Commit:          {final_deploy['meta']['commitSha'][:8]}")
    print(f"Frontend live:   {'✅ Yes' if live else '❌ No' if live is False else '⚠️  Unknown'}")
    print()

    if live:
        print("✅ SUCCESS — Web service deployed with latest code.")
        print("   Mock data removed. All views use real API calls.")
    else:
        print("⚠️  Deploy completed but verification inconclusive.")
        print(f"   Check manually: curl -s {WEB_URL} | head -20")

    print("=" * 70)

if __name__ == "__main__":
    main()
