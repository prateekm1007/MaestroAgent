# verify_maestro.ps1 — MaestroAgent Verification Harness
# Runs all checks against the live production API + local repo state.
# Output: JSON report saved to ~/MaestroVerification/reports/

param(
    [string]$RepoPath = "",
    [string]$BackendUrl = "https://maestroagent-production.up.railway.app",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Continue"
$report = @{
    timestamp = (Get-Date).ToUniversalTime().ToString("o")
    backend_url = $BackendUrl
    checks = @{}
    summary = @{ pass = 0; fail = 0; warn = 0 }
}

function Add-Check {
    param([string]$name, [string]$status, [string]$detail)
    $report.checks[$name] = @{ status = $status; detail = $detail }
    switch ($status) {
        "PASS" { $report.summary.pass++ }
        "FAIL" { $report.summary.fail++ }
        "WARN" { $report.summary.warn++ }
    }
    Write-Host "  [$status] $name : $detail"
}

# ── Find repo ──
if (-not $RepoPath) {
    $candidates = @(
        "$env:USERPROFILE\MaestroAgent"
        "$env:USERPROFILE\MaestroVerification\MaestroAgent"
        "C:\MaestroAgent"
        "$PWD"
    )
    foreach ($c in $candidates) {
        if (Test-Path "$c\download\MaestroAgent\maestro-personal\src\maestro_personal_shell\api.py") {
            $RepoPath = $c
            break
        }
    }
}

if (-not $RepoPath -or -not (Test-Path "$RepoPath\download\MaestroAgent\maestro-personal\src\maestro_personal_shell\api.py")) {
    Add-Check "repo_found" "FAIL" "MaestroAgent repo not found. Pass -RepoPath or clone to ~/MaestroAgent"
} else {
    Add-Check "repo_found" "PASS" $RepoPath
}

# ── 1. Backend health ──
try {
    $health = Invoke-RestMethod -Uri "$BackendUrl/api/health" -TimeoutSec 15
    $buildTime = $health.build_time
    $commit = $health.commit
    $isFresh = $buildTime -and ((Get-Date) - [DateTime]::Parse($buildTime)).TotalHours -lt 48
    Add-Check "backend_health" "PASS" "status=$($health.status) commit=$($commit.Substring(0,8)) build=$buildTime"
    if (-not $isFresh) {
        Add-Check "build_fresh" "WARN" "Build time is older than 48h: $buildTime"
    } else {
        Add-Check "build_fresh" "PASS" "Build time within 48h: $buildTime"
    }
} catch {
    Add-Check "backend_health" "FAIL" "Health check failed: $_"
}

# ── 2. Git local vs origin ──
if ($RepoPath -and (Test-Path "$RepoPath\.git")) {
    try {
        Push-Location $RepoPath
        git fetch origin 2>&1 | Out-Null
        $local = git rev-parse HEAD 2>&1
        $origin = git rev-parse origin/main 2>&1
        if ($local -eq $origin) {
            Add-Check "git_sync" "PASS" "Local matches origin/main: $($local.Substring(0,8))"
        } else {
            Add-Check "git_sync" "FAIL" "Local=$($local.Substring(0,8)) != origin=$($origin.Substring(0,8)) — unpushed commits"
        }
        Pop-Location
    } catch {
        Add-Check "git_sync" "WARN" "Git check failed: $_"
    }
} else {
    Add-Check "git_sync" "WARN" "No .git directory found"
}

# ── 3. Code checks (grep patterns) ──
if ($RepoPath) {
    $srcPath = "$RepoPath\download\MaestroAgent\maestro-personal\src\maestro_personal_shell"

    # P69: commitment_owner in reconcile.py
    $reconcileContent = Get-Content "$srcPath\reconcile.py" -Raw -ErrorAction SilentlyContinue
    if ($reconcileContent -and $reconcileContent -match "commitment_owner") {
        Add-Check "p69_owner_key" "PASS" "reconcile.py reads commitment_owner"
    } else {
        Add-Check "p69_owner_key" "FAIL" "reconcile.py does NOT read commitment_owner (P69 regression)"
    }

    # P66: no local imports of default_sqlite_path in ask.py
    $askContent = Get-Content "$srcPath\routers\ask.py" -Raw -ErrorAction SilentlyContinue
    if ($askContent) {
        $localImports = ([regex]::Matches($askContent, "from maestro_personal_shell\.db_util import default_sqlite_path")).Count
        if ($localImports -le 1) {
            Add-Check "p66_shadowing" "PASS" "ask.py has $localImports default_sqlite_path import(s) (module-level only)"
        } else {
            Add-Check "p66_shadowing" "FAIL" "ask.py has $localImports default_sqlite_path imports (P66 shadowing risk)"
        }

        # P66: no aliased Path imports
        $aliasedImports = ([regex]::Matches($askContent, "from pathlib import Path as")).Count
        if ($aliasedImports -eq 0) {
            Add-Check "p66_aliased" "PASS" "No aliased Path imports in ask.py"
        } else {
            Add-Check "p66_aliased" "FAIL" "Found $aliasedImports aliased Path imports in ask.py"
        }

        # P63: no demo-bypass-token in production code
        if ($askContent -notmatch "demo-bypass-token" -and (Get-Content "$srcPath\routers\auth.py" -Raw -ErrorAction SilentlyContinue) -notmatch "demo-bypass-token") {
            Add-Check "p63_bypass_token" "PASS" "No demo-bypass-token in production code"
        } else {
            # Check if it's gated
            $authContent = Get-Content "$srcPath\routers\auth.py" -Raw -ErrorAction SilentlyContinue
            if ($authContent -match "MAESTRO_LOCAL_DEV" -and $authContent -match "demo-bypass-token") {
                Add-Check "p63_bypass_token" "PASS" "demo-bypass-token is gated on MAESTRO_LOCAL_DEV"
            } else {
                Add-Check "p63_bypass_token" "FAIL" "demo-bypass-token found ungated in auth.py"
            }
        }
    }

    # Hardcoded DB paths check
    $hardcoded = Get-ChildItem $srcPath -Recurse -Filter "*.py" | Select-String -Pattern 'Path\(__file__\).*personal\.db' | Where-Object { $_.Path -notmatch "db_util.py" -and $_.Line -notmatch "^\s*#" -and $_.Line -notmatch "#.*Path" }
    if ($hardcoded.Count -eq 0) {
        Add-Check "hardcoded_db_paths" "PASS" "No hardcoded DB paths outside db_util.py"
    } else {
        Add-Check "hardcoded_db_paths" "FAIL" "Found $($hardcoded.Count) hardcoded paths: $($hardcoded | ForEach-Object { $_.Filename })"
    }
}

# ── 4. Live API checks ──
# Register a fresh user
try {
    $email = "verify-$(Get-Date -Format 'yyyyMMddHHmmss')@x.com"
    $regResp = Invoke-RestMethod -Uri "$BackendUrl/api/auth/register" -Method POST -ContentType "application/json" -Body (@{user_email=$email; password="audit-2026"; name="Verify"} | ConvertTo-Json) -TimeoutSec 30
    $token = $regResp.token
    Add-Check "register" "PASS" "Fresh user registered: $email"

    # Seed a signal
    Invoke-RestMethod -Uri "$BackendUrl/api/signals" -Method POST -Headers @{Authorization="Bearer $token"} -ContentType "application/json" -Body (@{entity="Maria"; text="I will send the proposal to Maria by Friday"; signal_type="commitment_made"} | ConvertTo-Json) -TimeoutSec 30 | Out-Null
    Add-Check "seed_signal" "PASS" "Signal created for Maria"

    # P43: ownership check — "What did I promise Maria?"
    $askResp = Invoke-RestMethod -Uri "$BackendUrl/api/ask" -Method POST -Headers @{Authorization="Bearer $token"} -ContentType "application/json" -Body (@{query="What did I promise Maria?"} | ConvertTo-Json) -TimeoutSec 90
    $answer = $askResp.answer
    if ($answer -match "Maria" -and ($answer -match "proposal" -or $answer -match "send")) {
        Add-Check "p43_ownership" "PASS" "P43: returns user's commitment to Maria"
    } else {
        Add-Check "p43_ownership" "FAIL" "P43: answer does not contain Maria's commitment: $($answer.Substring(0, [Math]::Min(100, $answer.Length)))"
    }

    # P60: third-party exclusion — "What did Maria promise?"
    $p60Resp = Invoke-RestMethod -Uri "$BackendUrl/api/ask" -Method POST -Headers @{Authorization="Bearer $token"} -ContentType "application/json" -Body (@{query="What did Maria promise?"} | ConvertTo-Json) -TimeoutSec 90
    $p60Answer = $p60Resp.answer
    if ($p60Answer -notmatch "I will send") {
        Add-Check "p60_exclusion" "PASS" "P60: third-party query does not leak user's commitment"
    } else {
        Add-Check "p60_exclusion" "FAIL" "P60: LEAK — 'I will send' found in third-party answer"
    }

    # P63: demo-bypass-token returns 401
    try {
        $bypassResp = Invoke-WebRequest -Uri "$BackendUrl/api/connectors" -Headers @{Authorization="Bearer demo-bypass-token"} -TimeoutSec 15
        Add-Check "p63_bypass_live" "FAIL" "demo-bypass-token returned $($bypassResp.StatusCode) (should be 401)"
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 401) {
            Add-Check "p63_bypass_live" "PASS" "demo-bypass-token returns 401 in production"
        } else {
            Add-Check "p63_bypass_live" "WARN" "demo-bypass-token returned $statusCode (expected 401)"
        }
    }

    # Rate limiting: 15 rapid logins
    $rateStatuses = @{}
    for ($i = 1; $i -le 15; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "$BackendUrl/api/auth/login" -Method POST -ContentType "application/json" -Body (@{user_email="rate-test-$i@x.com"; password="wrong"} | ConvertTo-Json) -TimeoutSec 15
            $code = $r.StatusCode
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
        }
        $rateStatuses[$code] = ($rateStatuses[$code] + 1)
    }
    if ($rateStatuses.ContainsKey(429) -and $rateStatuses[429] -gt 0) {
        Add-Check "rate_limiting" "PASS" "Rate limiting fires: $($rateStatuses[429])x429 out of 15 attempts"
    } else {
        Add-Check "rate_limiting" "WARN" "No 429s in 15 rapid attempts (statuses: $($rateStatuses.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }  -join ', '))"
    }

} catch {
    Add-Check "live_checks" "FAIL" "Live API check failed: $_"
}

# ── Save report ──
if (-not $OutputDir) {
    $OutputDir = "$env:USERPROFILE\MaestroVerification\reports"
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$reportFile = Join-Path $OutputDir "verification_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
$report | ConvertTo-Json -Depth 5 | Out-File -FilePath $reportFile -Encoding UTF8

# Clean old reports (keep last 30)
Get-ChildItem $OutputDir -Filter "verification_*.json" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force

Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "  PASS: $($report.summary.pass)" -ForegroundColor Green
Write-Host "  FAIL: $($report.summary.fail)" -ForegroundColor Red
Write-Host "  WARN: $($report.summary.warn)" -ForegroundColor Yellow
Write-Host "  Report: $reportFile" -ForegroundColor Gray
Write-Host ""

if ($report.summary.fail -gt 0) { exit 1 } else { exit 0 }
