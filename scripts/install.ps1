[CmdletBinding()]
param(
    [string]$Package = "audisor-local==0.2.0",
    [switch]$SkipCodexRegistration
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/."
}

uv tool install --force $Package
if (-not $SkipCodexRegistration) {
    audisor install-codex
}
