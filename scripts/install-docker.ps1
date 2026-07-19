[CmdletBinding()]
param(
    [string]$Image = "ghcr.io/itz1508/audisor:0.2.0",
    [switch]$SkipCodexRegistration
)

$ErrorActionPreference = "Stop"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required for the container installation path."
}

docker pull $Image
if (-not $SkipCodexRegistration) {
    codex mcp add audisor-docker -- docker run --rm -i --read-only --user 10001:10001 $Image mcp
}
