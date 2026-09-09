param(
    [switch]$ApproveProduction
)

$ErrorActionPreference = "Stop"

if (-not $ApproveProduction) {
    throw "Production promotion requires explicit approval: .\production-pipeline.ps1 -ApproveProduction"
}

& (Join-Path $PSScriptRoot "deploy.ps1") -Action Promote -ApproveProduction
exit $LASTEXITCODE
