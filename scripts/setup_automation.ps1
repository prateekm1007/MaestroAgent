# setup_automation.ps1 — Install MaestroAgent verification automation on Windows
# Creates: scheduled task (daily 09:00) + desktop shortcut + report directory

param(
    [string]$RepoPath = "$env:USERPROFILE\MaestroAgent",
    [string]$InstallDir = "$env:USERPROFILE\MaestroVerification"
)

$ErrorActionPreference = "Stop"

Write-Host "=== MaestroAgent Verification Setup ===" -ForegroundColor Cyan

# 1. Create install directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path "$InstallDir\reports" | Out-Null
Write-Host "  Install dir: $InstallDir" -ForegroundColor Green

# 2. Copy verify script
$verifyScript = Join-Path $RepoPath "scripts\verify_maestro.ps1"
if (-not (Test-Path $verifyScript)) {
    # Download from GitHub if not in local repo
    $verifyScript = Join-Path $InstallDir "verify_maestro.ps1"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/prateekm1007/MaestroAgent/main/scripts/verify_maestro.ps1" -OutFile $verifyScript
    Write-Host "  Downloaded verify_maestro.ps1 from GitHub" -ForegroundColor Green
} else {
    Copy-Item $verifyScript -Destination "$InstallDir\verify_maestro.ps1" -Force
    Write-Host "  Copied verify_maestro.ps1 from repo" -ForegroundColor Green
}

# 3. Clone/update repo if needed
$repoTarget = "$env:USERPROFILE\MaestroAgent"
if (-not (Test-Path "$repoTarget\.git")) {
    Write-Host "  Cloning MaestroAgent repo..." -ForegroundColor Yellow
    git clone "https://github.com/prateekm1007/MaestroAgent.git" $repoTarget 2>&1 | Out-Null
    Write-Host "  Repo cloned to $repoTarget" -ForegroundColor Green
} else {
    Write-Host "  Repo exists, pulling latest..." -ForegroundColor Yellow
    Push-Location $repoTarget
    git pull origin main 2>&1 | Out-Null
    Pop-Location
    Write-Host "  Repo updated" -ForegroundColor Green
}

# 4. Create scheduled task (daily 09:00)
$taskName = "MaestroAgent_DailyVerify"
$taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\verify_maestro.ps1`" -RepoPath `"$repoTarget`""
$taskTrigger = New-ScheduledTaskTrigger -Daily -At 9am
$taskSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

# Remove existing task if present
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Description "Daily MaestroAgent verification" -Force | Out-Null
Write-Host "  Scheduled task created: $taskName (daily 09:00)" -ForegroundColor Green

# 5. Create desktop shortcut
$shortcutPath = "$env:USERPROFILE\Desktop\MaestroAgent Verify.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\verify_maestro.ps1`" -RepoPath `"$repoTarget`""
$shortcut.IconLocation = "powershell.exe,0"
$shortcut.Description = "Run MaestroAgent verification checks"
$shortcut.Save()
Write-Host "  Desktop shortcut created: $shortcutPath" -ForegroundColor Green

# 6. Run first verification
Write-Host ""
Write-Host "Running first verification..." -ForegroundColor Yellow
& "$InstallDir\verify_maestro.ps1" -RepoPath $repoTarget

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host "  Daily task: $taskName at 09:00"
Write-Host "  Desktop shortcut: $shortcutPath"
Write-Host "  Reports: $InstallDir\reports\"
Write-Host "  To copy latest report: Get-Content (Get-ChildItem ~/MaestroVerification/reports/verification_*.json | Sort LastWriteTime -Desc | Select -First 1).FullName | Set-Clipboard"
