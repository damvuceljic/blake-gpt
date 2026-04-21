[CmdletBinding()]
param(
    [string]$SkillsRoot,
    [string]$CodexSkillsRoot,
    [string[]]$SkillName,
    [switch]$All,
    [switch]$Force,
    [ValidateSet('copy', 'junction')]
    [string]$Mode = 'copy',
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Write-Step {
    param([string]$Message)
    Write-Host "[install-repo-codex-skills] $Message"
}

$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($SkillsRoot)) {
    $SkillsRoot = Join-Path $repoRoot 'skills'
}

if ([string]::IsNullOrWhiteSpace($CodexSkillsRoot)) {
    $codexHome = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
        Join-Path $HOME '.codex'
    } else {
        $env:CODEX_HOME
    }
    $CodexSkillsRoot = Join-Path $codexHome 'skills'
}

if (!(Test-Path -LiteralPath $SkillsRoot)) {
    throw "Skills root not found: $SkillsRoot"
}

$availableSkills = Get-ChildItem -LiteralPath $SkillsRoot -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') } |
    Sort-Object Name

if ($All) {
    $skillsToInstall = $availableSkills
} else {
    if (!$SkillName -or $SkillName.Count -eq 0) {
        $availableList = $availableSkills.Name -join ', '
        throw "Specify -SkillName <name> for ad hoc install or pass -All to install everything. Available skills: $availableList"
    }
    $skillsToInstall = @()
    foreach ($name in $SkillName) {
        $match = $availableSkills | Where-Object { $_.Name -eq $name } | Select-Object -First 1
        if (!$match) {
            throw "Requested skill not found in repo skills root: $name"
        }
        $skillsToInstall += $match
    }
}

if (!$skillsToInstall -or $skillsToInstall.Count -eq 0) {
    throw "No skills selected for installation from: $SkillsRoot"
}

Write-Step "Repo skills root: $SkillsRoot"
Write-Step "Codex skills root: $CodexSkillsRoot"
Write-Step "Install mode: $Mode"
Write-Step "Skills: $($skillsToInstall.Name -join ', ')"

if ($DryRun) {
    Write-Step "[DRY-RUN] No files were changed."
    Write-Step "Restart Codex after a real install to pick up new skills."
    exit 0
}

if (!(Test-Path -LiteralPath $CodexSkillsRoot)) {
    New-Item -ItemType Directory -Path $CodexSkillsRoot | Out-Null
    Write-Step "Created Codex skills root: $CodexSkillsRoot"
}

foreach ($skill in $skillsToInstall) {
    $sourceSkillPath = $skill.FullName
    $destinationSkillPath = Join-Path $CodexSkillsRoot $skill.Name

    if (Test-Path -LiteralPath $destinationSkillPath) {
        if (!$Force) {
            throw "Destination exists: $destinationSkillPath. Re-run with -Force to replace it."
        }
        Remove-Item -LiteralPath $destinationSkillPath -Recurse -Force
        Write-Step "Removed existing skill: $($skill.Name)"
    }

    if ($Mode -eq 'junction') {
        New-Item -ItemType Junction -Path $destinationSkillPath -Target $sourceSkillPath | Out-Null
    } else {
        Copy-Item -LiteralPath $sourceSkillPath -Destination $CodexSkillsRoot -Recurse -Force
    }

    Write-Step "Installed skill: $($skill.Name)"
}

Write-Step "Installed $($skillsToInstall.Count) skill(s)."
Write-Step "Restart Codex to pick up new skills."
