param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
    $PythonPath = Join-Path $repository '.venv\Scripts\python.exe'
}
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'RemoteSigned', '-File', ('"' + $PSCommandPath + '"'), '-PythonPath', ('"' + $PythonPath + '"'))
    exit
}
try {
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw 'Prepare el entorno Python del proyecto antes de configurar la red.' }
    $basePython = & $PythonPath -E -s -c 'import sys; print(sys._base_executable)'
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo identificar el entorno Python.' }
    $baseFolder = Split-Path -Parent ([string]($basePython | Select-Object -Last 1))
    $programs = @($PythonPath, (Join-Path (Split-Path -Parent $PythonPath) 'pythonw.exe'), (Join-Path $baseFolder 'python.exe'), (Join-Path $baseFolder 'pythonw.exe')) | Select-Object -Unique
    $profiles = @(Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Private' })
    if ($profiles.Count -eq 0) { throw 'Windows no tiene una red privada activa. Selecciona Red privada para la red de confianza y repite este paso.' }
    # Cada instalación administra únicamente las reglas de su propio ejecutable.
    # El identificador depende de la ruta; nunca se retiran reglas de otra copia.
    foreach ($program in $programs) {
        if (-not (Test-Path -LiteralPath $program)) { continue }
        $rutaPrograma = [IO.Path]::GetFullPath($program)
        $algoritmo = [Security.Cryptography.SHA256]::Create()
        try {
            $resumen = [BitConverter]::ToString($algoritmo.ComputeHash([Text.Encoding]::UTF8.GetBytes($rutaPrograma.ToLowerInvariant()))).Replace('-', '').Substring(0, 16)
        } finally { $algoritmo.Dispose() }
        foreach ($tipo in @('TLS', 'WiFi')) {
            $nombre = 'Hemeroteca-' + $resumen + '-' + $tipo
            $existente = Get-NetFirewallRule -Name $nombre -ErrorAction SilentlyContinue
            if ($existente) {
                $filtro = Get-NetFirewallApplicationFilter -AssociatedNetFirewallRule $existente
                if (-not $filtro -or [IO.Path]::GetFullPath($filtro.Program) -ine $rutaPrograma) {
                    throw 'Existe una regla de red con el mismo nombre para otro programa. No se modificó.'
                }
                Remove-NetFirewallRule -InputObject $existente -ErrorAction Stop
            }
            if ($tipo -eq 'TLS') {
                New-NetFirewallRule -Name $nombre -DisplayName 'Hemeroteca - consulta y autorizacion' -Direction Inbound -Action Allow -Program $rutaPrograma -Protocol TCP -LocalPort 8765,8767 -Profile Private -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block -ErrorAction Stop | Out-Null
            } else {
                New-NetFirewallRule -Name $nombre -DisplayName 'Hemeroteca - deteccion de computadoras' -Direction Inbound -Action Allow -Program $rutaPrograma -Protocol UDP -LocalPort 8766 -Profile Private -RemoteAddress LocalSubnet -EdgeTraversalPolicy Block -ErrorAction Stop | Out-Null
            }
        }
    }
    Write-Host 'Listo. Hemeroteca puede comunicarse con las PC de tu red privada.'
    Write-Host 'Vuelve a la aplicacion y pulsa Buscar computadoras en la PC principal.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Pulsa Enter para cerrar'
    exit 1
}
Read-Host 'Pulsa Enter para cerrar'

