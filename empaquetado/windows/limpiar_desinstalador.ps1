param([string]$Directorio, [int]$ProcesoEspera)
$ErrorActionPreference = 'Stop'
# Se ejecuta tras cerrar el asistente, cuando el autoextraíble deja de estar abierto.
if ($ProcesoEspera -gt 0) { Wait-Process -Id $ProcesoEspera -Timeout 180 -ErrorAction SilentlyContinue }
try {
$Directorio = [IO.Path]::GetFullPath($Directorio)
$normal = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Hemeroteca-2.4.2-solo-consulta'
if ($Directorio -ine $normal -and (Split-Path -Leaf $Directorio) -notmatch '^Hemeroteca-Prueba-[a-f0-9]{32}$') { exit 1 }
$marcador = Join-Path $Directorio '.Hemeroteca-instalacion.json'
if (-not (Test-Path -LiteralPath $marcador)) { exit 0 }
$registro = Get-Content -LiteralPath $marcador -Raw -Encoding UTF8 | ConvertFrom-Json
if ($registro.identificador -ne 'Hemeroteca-2.4.2-solo-consulta') { exit 1 }
$ejecutable = Join-Path $Directorio 'Desinstalar_Hemeroteca.exe'
for ($intento=0; $intento -lt 50 -and (Test-Path -LiteralPath $ejecutable); $intento++) {
    try { Remove-Item -LiteralPath $ejecutable -Force -ErrorAction Stop }
    catch { Start-Sleep -Milliseconds 200 }
}
if (Test-Path -LiteralPath $ejecutable) { exit 1 }
foreach ($nombre in @('Desinstalar_Hemeroteca.exe', '.Hemeroteca-instalacion', '.Hemeroteca-instalacion.json')) {
    $archivo = [IO.Path]::GetFullPath((Join-Path $Directorio $nombre))
    if (-not $archivo.StartsWith($Directorio + '\', [StringComparison]::OrdinalIgnoreCase)) { exit 1 }
    if (Test-Path -LiteralPath $archivo) { Remove-Item -LiteralPath $archivo -Force }
}
if (@(Get-ChildItem -LiteralPath $Directorio -Force).Count -eq 0) { Remove-Item -LiteralPath $Directorio }
} finally {
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}
