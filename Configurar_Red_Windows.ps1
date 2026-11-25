$ErrorActionPreference = 'Stop'
try {
    $programa = Join-Path $PSScriptRoot 'Hemeroteca.exe'
    if (-not (Test-Path -LiteralPath $programa -PathType Leaf)) { throw 'Instala Hemeroteca 2.4.2 y ejecuta este comando desde la carpeta instalada.' }
    $script = Join-Path $PSScriptRoot 'firewall.ps1'
    $argumentos = '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "{0}" -Modo Configurar -Programa "{1}"' -f $script,$programa
    $proceso = Start-Process -FilePath "$PSHOME\powershell.exe" -Verb RunAs -WindowStyle Hidden -ArgumentList $argumentos -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { throw 'Windows no pudo crear las reglas de red.' }
    Write-Host 'Red privada lista. Abre Hemeroteca para activar el servidor o preparar esta PC.'
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
