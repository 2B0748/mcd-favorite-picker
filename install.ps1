#Requires -Version 5.1
<#
.SYNOPSIS
    Install the mcd-favorite-picker skill into a local skills directory.

.DESCRIPTION
    Copies skills/mcd-favorite-picker into the target skills folder.
    An existing installation is backed up first.
    This script never reads, writes or asks for any MCP token,
    and it does not modify any MCP connector configuration.

.EXAMPLE
    ./install.ps1
    ./install.ps1 -Dest "D:\tools\skills"
#>
[CmdletBinding()]
param(
    [string]$Dest = (Join-Path $env:USERPROFILE ".workbuddy\skills"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "skills\mcd-favorite-picker"

if (-not (Test-Path $src)) {
    Write-Error "Skill source not found: $src"
    exit 1
}

if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    Write-Host "Created: $Dest"
}

$target = Join-Path $Dest "mcd-favorite-picker"

if (Test-Path $target) {
    if (-not $Force) {
        $answer = Read-Host "Target exists. Backup and overwrite? [y/N]"
        if ($answer -notmatch '^[Yy]') {
            Write-Host "Cancelled."
            exit 0
        }
    }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backup = "$target.bak-$stamp"
    Move-Item -Path $target -Destination $backup
    Write-Host "Backed up old version to: $backup"
}

Copy-Item -Path $src -Destination $target -Recurse -Force

$count = (Get-ChildItem -Path $target -Recurse -File | Measure-Object).Count
Write-Host "Installed $count files to: $target"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Make sure the mcd-mcp connector is configured and trusted in your AI client."
Write-Host "  2. Start a new session and ask: what should I eat at McDonald's today?"
Write-Host ""
Write-Host "Self-test (offline, no token needed):"
Write-Host "  python `"$target\tests\run_tests.py`""
