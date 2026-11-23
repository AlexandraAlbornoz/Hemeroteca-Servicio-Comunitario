param(
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [Parameter(Mandatory=$true)][string]$WorkerPath,
    [Parameter(Mandatory=$true)][string]$DatabasePath,
    [Parameter(Mandatory=$true)][string]$SettingsPath,
    [Parameter(Mandatory=$true)][string]$NetworkPath,
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')][string]$At = '18:00',
    [switch]$Remove,
    [switch]$EjecutableAutonomo
)
$ErrorActionPreference = 'Stop'
if ($TaskName -notmatch '^Hemeroteca-Respaldo-[a-f0-9]{16}$') { throw 'Invalid task name.' }
if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    exit 0
}
foreach ($item in @($PythonPath, $WorkerPath, $DatabasePath, $SettingsPath)) {
    if (-not (Test-Path -LiteralPath $item -PathType Leaf)) { throw 'A required file is missing.' }
}
# Windows paths cannot contain a quote. Values are arguments, never evaluated as PowerShell code.
foreach ($item in @($WorkerPath, $DatabasePath, $SettingsPath, $NetworkPath)) {
    if ($item.Contains('"')) { throw 'Invalid path.' }
}
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = '"{0}" --database "{1}" --settings "{2}" --network "{3}"' -f $WorkerPath, $DatabasePath, $SettingsPath, $NetworkPath
if ($EjecutableAutonomo) {
    $arguments = '--backup-worker --database "{0}" --settings "{1}" --network "{2}"' -f $DatabasePath, $SettingsPath, $NetworkPath
}
$action = New-ScheduledTaskAction -Execute $PythonPath -Argument $arguments -WorkingDirectory (Split-Path -Parent $WorkerPath)
$daily = New-ScheduledTaskTrigger -Daily -At $At
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($daily, $logon) -Principal $principal -Settings $settings -Description 'Hemeroteca: respaldo cifrado diario configurado por el administrador maestro.' -Force | Out-Null
