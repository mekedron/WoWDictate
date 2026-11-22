<#
Installs the Dictate addon and the wow-dictate companion on Windows.

  .\install.ps1                      addon + companion (starts with Windows)
  .\install.ps1 -Part addon          addon only
  .\install.ps1 -WowDir "D:\Games\World of Warcraft\_forever_"

Run from PowerShell in the repository folder. If scripts are blocked:
  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
param(
    [ValidateSet("all", "addon", "companion")] [string] $Part = "all",
    [string] $WowDir = "",
    [string] $Flavor = "_forever_"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-WowDir {
    if ($WowDir) { return $WowDir }
    $keys = @(
        "HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft",
        "HKLM:\SOFTWARE\Blizzard Entertainment\World of Warcraft"
    )
    foreach ($key in $keys) {
        $install = (Get-ItemProperty -Path $key -Name InstallPath -ErrorAction SilentlyContinue).InstallPath
        if ($install) {
            # InstallPath points at one flavor folder (e.g. ...\_retail_\); use its parent.
            $base = Split-Path -Parent ($install.TrimEnd("\"))
            if (Test-Path (Join-Path $base $Flavor)) { return (Join-Path $base $Flavor) }
        }
    }
    foreach ($base in @("${env:ProgramFiles(x86)}\World of Warcraft", "$env:ProgramFiles\World of Warcraft")) {
        if (Test-Path (Join-Path $base $Flavor)) { return (Join-Path $base $Flavor) }
    }
    throw "World of Warcraft $Flavor folder not found; pass -WowDir"
}

function Install-Addon {
    $target = Join-Path (Find-WowDir) "Interface\AddOns\Dictate"
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -Force (Join-Path $Root "Dictate\*.toc"), (Join-Path $Root "Dictate\*.lua"), (Join-Path $Root "Dictate\*.xml") $target
    New-Item -ItemType Directory -Force -Path (Join-Path $target "Locales") | Out-Null
    Copy-Item -Force (Join-Path $Root "Dictate\Locales\*.lua") (Join-Path $target "Locales")
    Write-Host "addon -> $target"
}

function Get-Uv {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Host "installing uv (https://docs.astral.sh/uv/)"
        powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        $uv = Get-Command uv
    }
    return $uv.Source
}

function New-Shortcut([string] $Path, [string] $Target, [string] $Arguments, [string] $WorkDir) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath = $Target
    $link.Arguments = $Arguments
    $link.WorkingDirectory = $WorkDir
    $link.WindowStyle = 7  # minimized
    $link.Description = "wow-dictate: voice-to-chat companion for the Dictate WoW addon"
    $link.Save()
}

function Install-Companion {
    $uv = Get-Uv
    $project = Join-Path $Root "companion"
    & $uv sync --project $project -q
    & $uv run --project $project wow-dictate config | Out-Null
    # uvw.exe runs without a console window; it ships next to uv.exe.
    $uvw = Join-Path (Split-Path -Parent $uv) "uvw.exe"
    $runner = if (Test-Path $uvw) { $uvw } else { $uv }
    $arguments = "run --project `"$project`" wow-dictate run"
    $startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "WoW Dictate.lnk"
    $startup = Join-Path ([Environment]::GetFolderPath("Startup")) "WoW Dictate.lnk"
    New-Shortcut $startMenu $runner $arguments $project
    New-Shortcut $startup $runner $arguments $project
    # Restart a running companion (uv starts the wow-dictate.exe entry point).
    Get-Process -Name "wow-dictate" -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Process -FilePath $runner -ArgumentList $arguments -WorkingDirectory $project -WindowStyle Minimized
    $config = & $uv run --project $project wow-dictate config
    Write-Host "companion -> starts with Windows (Startup folder), running now"
    Write-Host "config    -> $config"
    Write-Host "log       -> $env:LOCALAPPDATA\wow-dictate\Logs\wow-dictate.log"
}

switch ($Part) {
    "addon" { Install-Addon }
    "companion" { Install-Companion }
    default { Install-Addon; Install-Companion }
}
