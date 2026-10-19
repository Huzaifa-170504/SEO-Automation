# ============================================================
# SEO-AUTOMATION - Project Initialization / Preflight Check
# ============================================================
#
# Purpose:
#   Verify that the local SEO automation environment is ready.
#
# This script:
#   - Does NOT modify .env
#   - Does NOT modify the database
#   - Prompts to launch Proton VPN when no active VPN adapter is detected
#   - Starts Ollama when its local API is unavailable
#   - Runs the test suite unless -SkipTests is supplied
#   - Starts the Telegram bot when all critical checks pass
#   - Does NOT expose API keys
#   - Performs a real Ollama/Qwen smoke test
#
# Exit codes:
#   0 = Ready
#   1 = One or more critical checks failed
#
# Optional switches:
#   -SkipTests       Skip the pytest verification step
#   -SkipVpnPrompt   Do not prompt to launch Proton VPN
#   -NoStartBot      Complete preflight without starting the Telegram bot
#
# ============================================================

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipVpnPrompt,
    [switch]$NoStartBot
)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

$ProjectRoot = Split-Path -Parent $PSScriptRoot

$VenvPython = Join-Path `
    $ProjectRoot `
    ".venv\Scripts\python.exe"

$EnvFile = Join-Path `
    $ProjectRoot `
    ".env"

$DatabaseFile = Join-Path `
    $ProjectRoot `
    "data\seo_automation.db"

$TelegramBotModule = "app.telegram.bot"

$LogDirectory = Join-Path `
    $ProjectRoot `
    "logs"

$TestTempDirectory = Join-Path `
    $ProjectRoot `
    ".test-tmp"

$BotPidFile = Join-Path `
    $ProjectRoot `
    "data\telegram_bot.pid"

$OllamaBaseUrl = "http://127.0.0.1:11434"
$QwenModel = "qwen-seo:4b"

$script:CriticalFailures = 0
$script:Warnings = 0
$script:BotStatus = "not checked"

# ------------------------------------------------------------
# Output helpers
# ------------------------------------------------------------

function Write-Section {
    param(
        [string]$Title
    )

    Write-Host ""
    Write-Host "============================================================" `
        -ForegroundColor DarkCyan

    Write-Host $Title `
        -ForegroundColor Cyan

    Write-Host "============================================================" `
        -ForegroundColor DarkCyan
}

function Write-Pass {
    param(
        [string]$Message
    )

    Write-Host "[PASS] $Message" `
        -ForegroundColor Green
}

function Write-Warn {
    param(
        [string]$Message
    )

    $script:Warnings++

    Write-Host "[WARN] $Message" `
        -ForegroundColor Yellow
}

function Write-Fail {
    param(
        [string]$Message
    )

    $script:CriticalFailures++

    Write-Host "[FAIL] $Message" `
        -ForegroundColor Red
}

function Write-Info {
    param(
        [string]$Message
    )

    Write-Host "[INFO] $Message" `
        -ForegroundColor Gray
}

function Test-OllamaApi {
    try {
        $null = Invoke-RestMethod `
            -Uri "$OllamaBaseUrl/api/tags" `
            -Method Get `
            -TimeoutSec 3

        return $true
    }
    catch {
        return $false
    }
}

function Test-VpnConnection {
    try {
        $VpnAdapters = @(
            Get-NetAdapter -ErrorAction Stop |
            Where-Object {
                $_.Status -eq "Up" -and
                (
                    $_.Name -match "Proton|VPN|WireGuard|TAP|TUN" -or
                    $_.InterfaceDescription -match "Proton|VPN|WireGuard|TAP|TUN"
                )
            }
        )

        return $VpnAdapters.Count -gt 0
    }
    catch {
        return $false
    }
}

function Get-ProtonVpnLauncher {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Proton\VPN\ProtonVPN.Launcher.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Proton\VPN\ProtonVPN.Launcher.exe"),
        (Join-Path $env:LOCALAPPDATA "ProtonVPN\ProtonVPN.Launcher.exe")
    )

    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return $Candidate
        }
    }

    return $null
}

function Get-TelegramBotProcesses {
    $BotScript = [regex]::Escape(
        (Join-Path $ProjectRoot "app\telegram\bot.py")
    )
    $BotModule = [regex]::Escape($TelegramBotModule)

    if (Test-Path -LiteralPath $BotPidFile -PathType Leaf) {
        $SavedPidText = [string](Get-Content -LiteralPath $BotPidFile -Raw)
        $SavedPidText = $SavedPidText.Trim()
        $SavedPid = 0

        if (
            [int]::TryParse($SavedPidText, [ref]$SavedPid) -and
            $SavedPid -gt 0
        ) {
            $SavedProcess = Get-Process `
                -Id $SavedPid `
                -ErrorAction SilentlyContinue

            if (
                $null -ne $SavedProcess -and
                $SavedProcess.ProcessName -in @("python", "pythonw")
            ) {
                return @(
                    [pscustomobject]@{
                        ProcessId = $SavedProcess.Id
                        Source = "pid file"
                    }
                )
            }
        }

        Remove-Item -LiteralPath $BotPidFile -Force -ErrorAction SilentlyContinue
    }

    try {
        return @(
            Get-CimInstance Win32_Process -ErrorAction Stop |
            Where-Object {
                $_.Name -in @("python.exe", "pythonw.exe") -and
                -not [string]::IsNullOrWhiteSpace($_.CommandLine) -and
                (
                    $_.CommandLine -match $BotScript -or
                    $_.CommandLine -match "-m\s+$BotModule(?:\s|$)"
                )
            }
        )
    }
    catch {
        Write-Info "Python command-line inspection is unavailable; using PID tracking."
        return @()
    }
}

# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

Clear-Host

Write-Host ""
Write-Host "SEO-AUTOMATION" `
    -ForegroundColor Cyan

Write-Host "Project Initialization / Preflight Check" `
    -ForegroundColor White

Write-Host ""
Write-Host "Project root: $ProjectRoot" `
    -ForegroundColor Gray

# ------------------------------------------------------------
# 1. Project root
# ------------------------------------------------------------

Write-Section "1. PROJECT ROOT"

if (Test-Path $ProjectRoot -PathType Container) {
    Write-Pass "Project root exists."
}
else {
    Write-Fail "Project root does not exist: $ProjectRoot"
}

# ------------------------------------------------------------
# 2. Python virtual environment
# ------------------------------------------------------------

Write-Section "2. PYTHON ENVIRONMENT"

if (Test-Path $VenvPython -PathType Leaf) {
    Write-Pass "Virtual environment Python found."

    try {
        $PythonVersion = & $VenvPython --version 2>&1

        Write-Info "Python: $PythonVersion"
    }
    catch {
        Write-Fail "Unable to execute virtual environment Python."
    }
}
else {
    Write-Fail "Virtual environment Python not found:"
    Write-Host "       $VenvPython" -ForegroundColor DarkGray
}

# ------------------------------------------------------------
# 3. Required Python imports
# ------------------------------------------------------------

Write-Section "3. PYTHON DEPENDENCIES"

if (Test-Path $VenvPython -PathType Leaf) {

    $RequiredModules = @(
        "httpx",
        "aiohttp",
        "dotenv",
        "pydantic",
        "sqlalchemy",
        "aiosqlite",
        "bs4",
        "lxml",
        "tenacity",
        "loguru",
        "google.genai",
        "telegram"
    )

    foreach ($Module in $RequiredModules) {

        try {
            $Result = & $VenvPython -c `
                "import $Module; print('OK')" 2>&1

            if ($LASTEXITCODE -eq 0) {
                Write-Pass "Python module available: $Module"
            }
            else {
                Write-Fail "Python module missing/unusable: $Module"
            }
        }
        catch {
            Write-Fail "Python module check failed: $Module"
        }
    }
}
else {
    Write-Fail "Skipping dependency checks because Python was not found."
}

# ------------------------------------------------------------
# 4. Environment configuration
# ------------------------------------------------------------

Write-Section "4. ENVIRONMENT CONFIGURATION"

if (Test-Path $EnvFile -PathType Leaf) {
    Write-Pass ".env file exists."
}
else {
    Write-Fail ".env file not found:"
    Write-Host "       $EnvFile" -ForegroundColor DarkGray
}

# Load .env values without printing secrets.
#
# This intentionally parses only the variables we need to
# validate. Values are never printed.

$EnvValues = @{}

if (Test-Path $EnvFile -PathType Leaf) {

    try {

        foreach ($Line in Get-Content $EnvFile) {

            $Trimmed = $Line.Trim()

            if (
                [string]::IsNullOrWhiteSpace($Trimmed) -or
                $Trimmed.StartsWith("#")
            ) {
                continue
            }

            if ($Trimmed -match '^([^=]+)=(.*)$') {

                $Key = $Matches[1].Trim()
                $Value = $Matches[2].Trim()

                if (
                    $Value.Length -ge 2 -and
                    (
                        (
                            $Value.StartsWith('"') -and
                            $Value.EndsWith('"')
                        ) -or
                        (
                            $Value.StartsWith("'") -and
                            $Value.EndsWith("'")
                        )
                    )
                ) {
                    $Value = $Value.Substring(
                        1,
                        $Value.Length - 2
                    )
                }

                $EnvValues[$Key] = $Value
            }
        }

        Write-Pass "Environment file parsed successfully."
    }
    catch {
        Write-Fail "Unable to parse .env file."
    }
}

# ------------------------------------------------------------
# 5. Database
# ------------------------------------------------------------

Write-Section "5. DATABASE"

if (Test-Path $DatabaseFile -PathType Leaf) {
    Write-Pass "SQLite database exists."

    $DatabaseSize = (
        Get-Item $DatabaseFile
    ).Length

    Write-Info "Database size: $DatabaseSize bytes"
}
else {
    Write-Warn "SQLite database does not exist yet."
    Write-Info "This may be normal for a fresh installation."
}

# ------------------------------------------------------------
# 6. VPN connection
# ------------------------------------------------------------

Write-Section "6. VPN CONNECTION"

if (Test-VpnConnection) {
    Write-Pass "An active VPN network adapter was detected."
}
elseif ($SkipVpnPrompt) {
    Write-Warn "No active VPN adapter was detected; prompt skipped by request."
}
else {
    Write-Warn "No active VPN network adapter was detected."
    $VpnAnswer = Read-Host "Launch Proton VPN so you can connect? [Y/N]"

    if ($VpnAnswer -match '^(?i:y|yes)$') {
        $ProtonVpnLauncher = Get-ProtonVpnLauncher

        if ($null -eq $ProtonVpnLauncher) {
            Write-Warn "Proton VPN is not installed in a recognized location."
            Write-Info "Open your VPN client manually before continuing."
        }
        else {
            try {
                Start-Process -FilePath $ProtonVpnLauncher
                Write-Info "Proton VPN opened. Connect using the Proton VPN window."
                $null = Read-Host "After connecting, press Enter to continue"

                if (Test-VpnConnection) {
                    Write-Pass "VPN connection is active."
                }
                else {
                    Write-Warn "A VPN connection is still not detected."
                }
            }
            catch {
                Write-Warn "Unable to launch Proton VPN."
                Write-Info $_.Exception.Message
            }
        }
    }
    else {
        Write-Warn "Continuing without a detected VPN connection."
    }
}

# ------------------------------------------------------------
# 7. Internet connectivity
# ------------------------------------------------------------

Write-Section "7. INTERNET CONNECTIVITY"

try {

    $InternetResponse = Invoke-WebRequest `
        -Uri "https://www.google.com" `
        -Method Head `
        -TimeoutSec 15 `
        -UseBasicParsing

    if (
        $InternetResponse.StatusCode -ge 200 -and
        $InternetResponse.StatusCode -lt 500
    ) {
        Write-Pass "Internet connectivity is available."
    }
    else {
        Write-Warn "Internet returned HTTP $($InternetResponse.StatusCode)."
    }
}
catch {
    Write-Fail "Internet connectivity check failed."
    Write-Info $_.Exception.Message
}

# ------------------------------------------------------------
# 8. Ollama server
# ------------------------------------------------------------

Write-Section "8. OLLAMA SERVER"

$OllamaAvailable = $false

if (Test-OllamaApi) {
    $OllamaAvailable = $true
    Write-Pass "Ollama server is reachable."
    Write-Info "Endpoint: $OllamaBaseUrl"
}
else {
    Write-Info "Ollama is not reachable; attempting to start 'ollama serve'."
    $OllamaCommand = Get-Command "ollama" -ErrorAction SilentlyContinue

    if ($null -eq $OllamaCommand) {
        Write-Fail "Ollama is unavailable and the ollama executable was not found."
    }
    else {
        try {
            Start-Process `
                -FilePath $OllamaCommand.Source `
                -ArgumentList "serve" `
                -WindowStyle Hidden

            for ($Attempt = 1; $Attempt -le 30; $Attempt++) {
                Start-Sleep -Seconds 1
                if (Test-OllamaApi) {
                    $OllamaAvailable = $true
                    break
                }
            }

            if ($OllamaAvailable) {
                Write-Pass "Ollama server started successfully."
                Write-Info "Endpoint: $OllamaBaseUrl"
            }
            else {
                Write-Fail "Ollama did not become ready within 30 seconds."
            }
        }
        catch {
            Write-Fail "Unable to start Ollama."
            Write-Info $_.Exception.Message
        }
    }
}

# ------------------------------------------------------------
# 9. Qwen model availability
# ------------------------------------------------------------

Write-Section "9. QWEN MODEL"

$QwenAvailable = $false

if ($OllamaAvailable) {

    try {

        $Models = Invoke-RestMethod `
            -Uri "$OllamaBaseUrl/api/tags" `
            -Method Get `
            -TimeoutSec 10

        $ModelNames = @(
            $Models.models |
            ForEach-Object {
                $_.name
            }
        )

        if ($ModelNames -contains $QwenModel) {

            $QwenAvailable = $true

            Write-Pass "Qwen model is installed: $QwenModel"
        }
        else {

            Write-Fail "Required Qwen model was not found: $QwenModel"

            if ($ModelNames.Count -gt 0) {
                Write-Info "Available Ollama models:"
                foreach ($ModelName in $ModelNames) {
                    Write-Host "       $ModelName" `
                        -ForegroundColor DarkGray
                }
            }
            else {
                Write-Info "Ollama reports no installed models."
            }
        }
    }
    catch {
        Write-Fail "Unable to inspect Ollama models."
        Write-Info $_.Exception.Message
    }
}
else {
    Write-Fail "Skipping Qwen model check because Ollama is unavailable."
}

# ------------------------------------------------------------
# 10. REAL Qwen generation smoke test
# ------------------------------------------------------------

Write-Section "10. REAL QWEN GENERATION TEST"

if ($QwenAvailable) {

    try {

        $QwenPayload = @{
            model = $QwenModel

            messages = @(
                @{
                    role = "system"
                    content = "You are a test assistant."
                },
                @{
                    role = "user"
                    content = "Reply with exactly: QWEN_OK"
                }
            )

            stream = $false

            options = @{
                temperature = 0
            }
        } | ConvertTo-Json -Depth 10

        Write-Info "Sending a minimal test request to Qwen..."

        $QwenResponse = Invoke-RestMethod `
            -Uri "$OllamaBaseUrl/api/chat" `
            -Method Post `
            -ContentType "application/json" `
            -Body $QwenPayload `
            -TimeoutSec 180

        $QwenText = $QwenResponse.message.content

        if ([string]::IsNullOrWhiteSpace($QwenText)) {
            Write-Fail "Qwen returned an empty response."
        }
        else {

            Write-Pass "Qwen generated a real response."

            $CleanQwenText = $QwenText.Trim()

            if ($CleanQwenText -eq "QWEN_OK") {
                Write-Pass "Qwen smoke-test response matched exactly."
            }
            else {
                Write-Warn "Qwen responded, but not with the exact expected text."
                Write-Info "Response: $CleanQwenText"
            }
        }
    }
    catch {
        Write-Fail "Real Qwen generation test failed."
        Write-Info $_.Exception.Message
    }
}
else {
    Write-Fail "Skipping Qwen generation test because the model is unavailable."
}

# ------------------------------------------------------------
# 11. Gemini configuration
# ------------------------------------------------------------

Write-Section "11. GEMINI CONFIGURATION"

$GeminiApiKey = $null
$GeminiModel = $null

if ($EnvValues.ContainsKey("GEMINI_API_KEY")) {
    $GeminiApiKey = $EnvValues["GEMINI_API_KEY"]
}

if ($EnvValues.ContainsKey("GEMINI_MODEL")) {
    $GeminiModel = $EnvValues["GEMINI_MODEL"]
}

if (
    -not [string]::IsNullOrWhiteSpace($GeminiApiKey)
) {
    Write-Pass "GEMINI_API_KEY is configured."
}
else {
    Write-Warn "GEMINI_API_KEY is not configured."
}

if (
    -not [string]::IsNullOrWhiteSpace($GeminiModel)
) {
    Write-Pass "GEMINI_MODEL is configured: $GeminiModel"
}
else {
    Write-Info "GEMINI_MODEL is not explicitly configured."
    Write-Info "GeminiClient will use its default model."
}

# ------------------------------------------------------------
# 12. Telegram configuration
# ------------------------------------------------------------

Write-Section "12. TELEGRAM CONFIGURATION"

$TelegramToken = $null

if ($EnvValues.ContainsKey("TELEGRAM_BOT_TOKEN")) {
    $TelegramToken = $EnvValues["TELEGRAM_BOT_TOKEN"]
}

if (
    -not [string]::IsNullOrWhiteSpace($TelegramToken)
) {
    Write-Pass "TELEGRAM_BOT_TOKEN is configured."
}
else {
    Write-Warn "TELEGRAM_BOT_TOKEN is not configured."
}

if ($EnvValues.ContainsKey("TELEGRAM_PROXY_URL")) {
    if (
        -not [string]::IsNullOrWhiteSpace(
            $EnvValues["TELEGRAM_PROXY_URL"]
        )
    ) {
        Write-Pass "TELEGRAM_PROXY_URL is configured."
    }
    else {
        Write-Info "TELEGRAM_PROXY_URL exists but is empty."
    }
}
else {
    Write-Info "TELEGRAM_PROXY_URL is not configured."
}

# ------------------------------------------------------------
# 13. Project source files
# ------------------------------------------------------------

Write-Section "13. PROJECT SOURCE"

$RequiredFiles = @(
    "app\telegram\bot.py",
    "app\models\qwen.py",
    "app\models\gemini.py",
    "app\models\issue.py",
    "app\workflow\orchestrator.py",
    "app\workflow\state.py",
    "app\agents\manager.py"
)

foreach ($RelativePath in $RequiredFiles) {

    $FullPath = Join-Path `
        $ProjectRoot `
        $RelativePath

    if (Test-Path $FullPath -PathType Leaf) {
        Write-Pass "Found: $RelativePath"
    }
    else {
        Write-Fail "Missing: $RelativePath"
    }
}

# ------------------------------------------------------------
# 14. Project tests
# ------------------------------------------------------------

Write-Section "14. PROJECT TESTS"

if ($SkipTests) {
    Write-Info "Test suite skipped by request."
}
elseif (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Fail "Cannot run tests because virtual environment Python is missing."
}
else {
    try {
        if (-not (Test-Path -LiteralPath $TestTempDirectory -PathType Container)) {
            $null = New-Item `
                -ItemType Directory `
                -Path $TestTempDirectory `
                -Force
        }

        $PreviousTemp = $env:TEMP
        $PreviousTmp = $env:TMP
        $env:TEMP = $TestTempDirectory
        $env:TMP = $TestTempDirectory

        Push-Location $ProjectRoot
        try {
            & $VenvPython -m pytest -q
            $TestExitCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
            $env:TEMP = $PreviousTemp
            $env:TMP = $PreviousTmp
        }

        if ($TestExitCode -eq 0) {
            Write-Pass "Project test suite passed."
        }
        else {
            Write-Fail "Project test suite failed with exit code $TestExitCode."
        }
    }
    catch {
        Write-Fail "Unable to run the project test suite."
        Write-Info $_.Exception.Message
    }
}

# ------------------------------------------------------------
# 15. Telegram bot process
# ------------------------------------------------------------

Write-Section "15. TELEGRAM BOT"

$RunningBots = @(Get-TelegramBotProcesses)

if ($RunningBots.Count -gt 0) {
    $script:BotStatus = "already running"
    Write-Pass "Telegram bot is already running."
    Write-Info "Process ID: $($RunningBots[0].ProcessId)"
}
elseif ($NoStartBot) {
    $script:BotStatus = "start skipped"
    Write-Info "Telegram bot startup skipped by request."
}
elseif ($script:CriticalFailures -gt 0) {
    $script:BotStatus = "not started because preflight failed"
    Write-Warn "Telegram bot was not started because critical checks failed."
}
elseif ([string]::IsNullOrWhiteSpace($TelegramToken)) {
    $script:BotStatus = "not started because token is missing"
    Write-Fail "Telegram bot cannot start without TELEGRAM_BOT_TOKEN."
}
else {
    try {
        if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
            $null = New-Item `
                -ItemType Directory `
                -Path $LogDirectory `
                -Force
        }

        $LogTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $BotStdoutLog = Join-Path `
            $LogDirectory `
            "telegram_bot_$LogTimestamp.stdout.log"
        $BotStderrLog = Join-Path `
            $LogDirectory `
            "telegram_bot_$LogTimestamp.stderr.log"

        $BotProcess = Start-Process `
            -FilePath $VenvPython `
            -ArgumentList @("-m", $TelegramBotModule) `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $BotStdoutLog `
            -RedirectStandardError $BotStderrLog `
            -PassThru

        Start-Sleep -Seconds 3
        $BotProcess.Refresh()

        if ($BotProcess.HasExited) {
            $script:BotStatus = "failed to start"
            Remove-Item `
                -LiteralPath $BotPidFile `
                -Force `
                -ErrorAction SilentlyContinue
            Write-Fail "Telegram bot exited immediately with code $($BotProcess.ExitCode)."
            Write-Info "Error log: $BotStderrLog"
        }
        else {
            $script:BotStatus = "started"
            $BotPidDirectory = Split-Path -Parent $BotPidFile
            if (-not (Test-Path -LiteralPath $BotPidDirectory -PathType Container)) {
                $null = New-Item `
                    -ItemType Directory `
                    -Path $BotPidDirectory `
                    -Force
            }
            Set-Content `
                -LiteralPath $BotPidFile `
                -Value $BotProcess.Id `
                -Encoding ascii
            Write-Pass "Telegram bot started in the background."
            Write-Info "Process ID: $($BotProcess.Id)"
            Write-Info "Output log: $BotStdoutLog"
            Write-Info "Error log: $BotStderrLog"
        }
    }
    catch {
        $script:BotStatus = "failed to start"
        Write-Fail "Unable to start the Telegram bot."
        Write-Info $_.Exception.Message
    }
}

# ------------------------------------------------------------
# 16. Final summary
# ------------------------------------------------------------

Write-Section "INITIALIZATION SUMMARY"

if ($script:CriticalFailures -eq 0) {

    Write-Host ""
    Write-Host "SYSTEM STATUS: READY" `
        -ForegroundColor Green

    Write-Host ""

    Write-Host "Critical failures: 0" `
        -ForegroundColor Green

    Write-Host "Warnings: $($script:Warnings)" `
        -ForegroundColor Yellow

    Write-Host ""

    Write-Host "The project passed all critical preflight checks." `
        -ForegroundColor Green

    Write-Host "Telegram bot: $($script:BotStatus)" `
        -ForegroundColor Green

    exit 0
}
else {

    Write-Host ""
    Write-Host "SYSTEM STATUS: NOT READY" `
        -ForegroundColor Red

    Write-Host ""

    Write-Host "Critical failures: $($script:CriticalFailures)" `
        -ForegroundColor Red

    Write-Host "Warnings: $($script:Warnings)" `
        -ForegroundColor Yellow

    Write-Host ""

    Write-Host "Fix the failed checks before starting the automation." `
        -ForegroundColor Yellow

    Write-Host "Telegram bot: $($script:BotStatus)" `
        -ForegroundColor Gray

    exit 1
}
