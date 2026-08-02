$appDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$batFile = Join-Path $appDir "run_app.bat"
$iconFile = Join-Path $appDir "icon.ico"
$shortcutPath = "$env:USERPROFILE\Desktop\Meeting Notes AI.lnk"

$WshShell  = New-Object -ComObject WScript.Shell
$Shortcut  = $WshShell.CreateShortcut($shortcutPath)
$Shortcut.TargetPath       = $batFile
$Shortcut.WorkingDirectory = $appDir
$Shortcut.Description      = "Meeting Notes AI"

if (Test-Path $iconFile) {
    $Shortcut.IconLocation = $iconFile
}

$Shortcut.Save()
Write-Host "Desktop shortcut created: $shortcutPath"
