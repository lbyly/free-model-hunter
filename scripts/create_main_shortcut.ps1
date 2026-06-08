# PowerShell script to create a desktop shortcut for Free-Model-Hub's backend main.py
# This script locates the Python interpreter, resolves the path to backend\main.py, and creates a .lnk shortcut on the user's desktop.

# Resolve Python executable (uses the first python found in PATH)
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Write-Error "Python executable not found in PATH. Please ensure Python is installed and added to PATH."
    exit 1
}

# Determine the repository root (parent of the scripts directory)
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir  # repo root is the parent directory of the scripts folder

# Determine the absolute path to backend\main.py
$target = Join-Path $repoRoot "backend\main.py"
if (-not (Test-Path $target)) {
    Write-Error "Cannot locate backend\main.py at $target"
    exit 1
}

# Resolve the user's desktop folder
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop "FreeModelHub Backend Main.lnk"

# Create the shortcut using COM object
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
# Escape double quotes around the argument path using backticks
$shortcut.Arguments = "`"$target`""
$shortcut.WorkingDirectory = Split-Path $target

# Optional: set a custom icon if an icon file exists next to main.py
$iconPath = Join-Path (Split-Path $target) "icon.ico"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}

$shortcut.Save()
Write-Host "✅ Desktop shortcut created at $shortcutPath"
