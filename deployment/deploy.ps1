param(
    [ValidateSet("Build", "Stage", "Promote", "Rollback", "Smoke", "Down", "Status")]
    [string]$Action = "Status",
    [string]$ImageRef,
    [switch]$ApproveProduction
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
$EnvFile = Join-Path $ProjectRoot "backend\.env"
$StateDir = Join-Path $PSScriptRoot "state"
$AppCompose = Join-Path $PSScriptRoot "docker-compose.local.yml"
$OllamaCompose = Join-Path $PSScriptRoot "docker-compose.ollama.yml"

if (-not (Test-Path $EnvFile)) {
    throw "Missing backend\.env. Copy backend\.env.example if needed and set API_TOKEN and GROQ_API_KEY."
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function StatePath([string]$Name) {
    return (Join-Path $StateDir $Name)
}

function Read-State([string]$Name) {
    $path = StatePath $Name
    if (Test-Path $path) {
        return (Get-Content $path -Raw).Trim()
    }
    return $null
}

function Write-State([string]$Name, [string]$Value) {
    Set-Content -Path (StatePath $Name) -Value $Value -NoNewline
}

function Invoke-Compose([string]$Project, [int]$Port, [string]$Image, [string[]]$ComposeAction) {
    $oldImage = $env:APP_IMAGE
    $oldPort = $env:APP_PORT
    $env:APP_IMAGE = $Image
    $env:APP_PORT = "$Port"
    try {
        & docker compose --env-file $EnvFile -f $AppCompose -p $Project @ComposeAction
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Compose failed for $Project."
        }
    }
    finally {
        $env:APP_IMAGE = $oldImage
        $env:APP_PORT = $oldPort
    }
}

function Ensure-Ollama {
    & docker compose --env-file $EnvFile -f $OllamaCompose -p agentic-ops-ollama up -d
    if ($LASTEXITCODE -ne 0) {
        throw "The Ollama stack could not start."
    }

    $initId = (& docker compose --env-file $EnvFile -f $OllamaCompose -p agentic-ops-ollama ps -q ollama-init).Trim()
    if (-not $initId) {
        throw "The Ollama model-pull container was not created."
    }
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        $initState = (& docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' $initId).Trim()
        if ($initState -eq "exited 0") {
            return
        }
        if ($initState -like "exited *") {
            throw "The Ollama model pull failed: $initState"
        }
        Start-Sleep -Seconds 2
    }
    throw "The Ollama model pull did not finish within 120 seconds."
}

function Build-LocalImage {
    $tag = "agentic-ops-dashboard:local-$(Get-Date -Format yyyyMMddHHmmss)"
    & docker build --tag $tag $ProjectRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "The local application image could not be built."
    }
    Write-State "staged-image.txt" $tag
    Write-Host "Built $tag"
    return $tag
}

function Resolve-Image {
    if ($ImageRef) {
        if ($ImageRef.StartsWith("ghcr.io/")) {
            & docker pull $ImageRef | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw "The requested GHCR image could not be pulled."
            }
        }
        return $ImageRef
    }

    $staged = Read-State "staged-image.txt"
    if ($staged) {
        return $staged
    }
    return (Build-LocalImage)
}

function Invoke-Smoke([int]$Port) {
    $baseUrl = "http://127.0.0.1:$Port"
    $lastError = $null
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        try {
            $health = Invoke-RestMethod "$baseUrl/health"
            $ready = Invoke-RestMethod "$baseUrl/ready"
            if ($health.status -eq "ok" -and $ready.status -eq "ready") {
                Write-Output "Smoke test passed: $baseUrl"
                return
            }
            $lastError = "health=$($health.status), ready=$($ready.status)"
        }
        catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    }
    throw "Smoke test failed at $baseUrl. Last result: $lastError"
}

switch ($Action) {
    "Build" {
        Build-LocalImage | Out-Host
    }
    "Stage" {
        Ensure-Ollama
        $image = Resolve-Image
        Write-State "staged-image.txt" $image
        Invoke-Compose "agentic-ops-staging" 8001 $image @("up", "-d")
        Invoke-Smoke 8001
        Write-Output "Staging URL: http://localhost:8001/"
    }
    "Promote" {
        if (-not $ApproveProduction) {
            throw "Production is protected. Run deployment\production-pipeline.ps1 -ApproveProduction."
        }
        Ensure-Ollama
        $image = Read-State "staged-image.txt"
        if (-not $image) {
            throw "No staged image found. Run -Action Stage first."
        }
        $current = Read-State "production-image.txt"
        if ($current) {
            Write-State "previous-image.txt" $current
        }
        Write-State "production-image.txt" $image
        Invoke-Compose "agentic-ops-production" 8000 $image @("up", "-d")
        try {
            Invoke-Smoke 8000
        }
        catch {
            if ($current) {
                Write-State "production-image.txt" $current
                Invoke-Compose "agentic-ops-production" 8000 $current @("up", "-d")
            }
            throw
        }
        Write-Output "Production URL: http://localhost:8000/"
    }
    "Rollback" {
        Ensure-Ollama
        $previous = Read-State "previous-image.txt"
        if (-not $previous) {
            throw "No previous production image has been recorded."
        }
        Write-State "production-image.txt" $previous
        Invoke-Compose "agentic-ops-production" 8000 $previous @("up", "-d")
        Invoke-Smoke 8000
        Write-Output "Rolled back to: $previous"
    }
    "Smoke" {
        Invoke-Smoke 8000
    }
    "Down" {
        & docker compose --env-file $EnvFile -f $AppCompose -p agentic-ops-staging down
        & docker compose --env-file $EnvFile -f $AppCompose -p agentic-ops-production down
        & docker compose --env-file $EnvFile -f $OllamaCompose -p agentic-ops-ollama down
    }
    "Status" {
        Write-Output "Staged image: $(Read-State 'staged-image.txt')"
        Write-Output "Production image: $(Read-State 'production-image.txt')"
        Write-Output "Previous image: $(Read-State 'previous-image.txt')"
        & docker ps --filter "name=agentic-ops" --format "table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}"
    }
}
