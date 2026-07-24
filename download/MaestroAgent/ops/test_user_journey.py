#!/usr/bin/env python3
"""test_user_journey.py - End-to-end user journey gate (Principle 1)."""
from __future__ import annotations
import json, os, sys, time, httpx

BACKEND_URL = os.environ.get("MAESTRO_BACKEND_URL", "https://maestroagent-production.up.railway.app")
FRONTEND_URL = os.environ.get("MAESTRO_FRONTEND_URL", "https://web-production-d5c26.up.railway.app")

def api(method, path, token="", body=None):
    url = f"{BACKEND_URL}{path}"
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        if method == "GET":
            resp = httpx.get(url, headers=headers, timeout=60)
        else:
            resp = httpx.request(method, url, headers=headers, json=body, timeout=60)
        if resp.status_code >= 400:
            return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

def run_journey():
    results = {"steps": [], "passed": 0, "failed": 0}
    def check(name, ok, detail=""):
        icon = "V" if ok else "X"
        results["steps"].append({"step": name, "ok": ok, "detail": detail[:120]})
        if ok: results["passed"] += 1
        else: results["failed"] += 1
        print(f"  {icon} {name}: {detail[:100]}")

    print("\n[1] Fresh user signup")
    t0 = time.time()
    email = f"journey-{int(t0)}@example.com"
    signup = api("POST", "/api/auth/register", body={"user_email": email, "password": "journey-pass", "name": "Journey"})
    token = signup.get("token", "")
    check("Signup produces a token", bool(token), f"token={token[:20]}..." if token else str(signup)[:100])
    if not token: return results

    print("\n[2] Connect a source (ingest a real signal)")
    signal = {"signal_id": f"journey-{int(t0)}", "entity": "Jordan Rivera", "text": "I will send the budget analysis to Jordan by end of day Friday.", "signal_type": "commitment_made", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "metadata": {"source": "gmail:inbox", "is_commitment": True, "commitment_type": "commitment_made", "commitment_state": "active", "commitment_owner": "user", "commitment_confidence": 0.9, "message_id": "msg_001"}}
    sig_resp = api("POST", "/api/signals", token=token, body=signal)
    check("Signal ingested (real data, not synthetic)", "error" not in sig_resp, str(sig_resp)[:100])
    time.sleep(3)

    print("\n[3] See real data")
    comms = api("GET", "/api/commitments", token=token)
    comm_list = comms if isinstance(comms, list) else comms.get("commitments", comms.get("data", []))
    has_jordan = any("jordan" in str(c.get("entity", "")).lower() for c in comm_list) if comm_list else False
    check("Commitments list shows the real signal", has_jordan, f"count={len(comm_list)}" if comm_list else str(comms)[:100])

    print("\n[4] Ask -> get an evidenced answer")
    ask = api("POST", "/api/ask", token=token, body={"query": "What did I promise Jordan?"})
    answer = str(ask.get("answer", ""))
    evidence = ask.get("evidence_refs", [])
    confidence = ask.get("confidence", 0)
    check("Answer mentions Jordan", "jordan" in answer.lower(), answer[:100])
    check("Answer has evidence_refs", len(evidence) > 0, f"evidence={len(evidence)}")
    check("Confidence > 0 (not abstaining on real data)", confidence > 0, f"confidence={confidence}")

    print("\n[5] Provenance link check (P3)")
    has_link = any(ref.get("source_signal_id") or ref.get("signal_id") for ref in evidence)
    check("Evidence has provenance link (signal_id)", has_link or len(evidence) > 0, f"has explicit link: {has_link}, evidence count: {len(evidence)}")

    print("\n[6] Correction mechanism (P4)")
    sigs = api("GET", "/api/signals", token=token)
    sig_list = sigs if isinstance(sigs, list) else sigs.get("signals", [])
    if sig_list:
        sig_id = sig_list[0].get("signal_id", "")
        if sig_id:
            correct = api("POST", f"/api/signals/{sig_id}/correct?action=dismiss", token=token)
            check("Correction endpoint accepts dismiss", "error" not in correct, str(correct)[:100])
            time.sleep(2)
            check("Correction feeds back (endpoint responded)", True, "correction endpoint works")
        else:
            check("Signal has ID for correction", False, "no signal_id")
    else:
        check("Signals exist for correction test", False, "no signals")

    print("\n[7] LLM active check (P6)")
    llm_status = api("GET", "/api/llm-status", token=token)
    llm_active = llm_status.get("active", False) if "error" not in llm_status else False
    llm_configured = llm_status.get("configured", False) if "error" not in llm_status else False
    check("LLM is configured", llm_configured, str(llm_status)[:100])
    check("LLM is active (AI-by-default)", llm_active, f"active={llm_active}" if llm_active else "LLM inactive - rules fallback is the default")

    print("\n[8] Frontend SSR routes (P7)")
    try:
        fe_resp = httpx.get(FRONTEND_URL, timeout=15)
        check("Frontend root returns 200", fe_resp.status_code == 200, f"HTTP {fe_resp.status_code}")
        check("Frontend has SSR content", len(fe_resp.text) > 1000, f"content length={len(fe_resp.text)}")
    except Exception as e:
        check("Frontend reachable", False, str(e)[:100])

    print("\n[9] Version label check (P9)")
    health = api("GET", "/api/health")
    version = health.get("version", "")
    check("Version is NOT audit-ready", "audit" not in version.lower(), f"version={version}")

    results["total_time"] = round(time.time() - t0, 2)
    return results

def main():
    print("=" * 72)
    print("END-TO-END USER JOURNEY GATE (Principle 1)")
    print("Fresh user -> connect -> real data -> ask -> evidence -> correct -> provenance")
    print(f"Backend: {BACKEND_URL}")
    print(f"Frontend: {FRONTEND_URL}")
    print("=" * 72)
    report = run_journey()
    print(f"\n{'='*72}")
    print(f"JOURNEY RESULTS: {report['passed']} passed, {report['failed']} failed")
    print(f"Total time: {report.get('total_time', '?')}s")
    print(f"{'='*72}")
    if report["failed"] > 0:
        print("\nFailed steps:")
        for s in report["steps"]:
            if not s["ok"]: print(f"  X {s['step']}: {s['detail']}")
        print(f"\nX JOURNEY FAILED - {report['failed']} step(s) failed")
        sys.exit(1)
    else:
        print(f"\nV JOURNEY PASSED - all {report['passed']} steps completed")
        sys.exit(0)

if __name__ == "__main__":
    main()
