$ErrorActionPreference = 'Stop'
$desinstalador = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Hemeroteca-2.4.2-solo-consulta\Desinstalar_Hemeroteca.exe'
if (Test-Path -LiteralPath $desinstalador) {
    Start-Process -FilePath $desinstalador -WindowStyle Normal
} else {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show('No hay una instalación de Hemeroteca para desinstalar. Instala Hemeroteca 2.4.2 para acceder a la desinstalación total.', 'Hemeroteca') | Out-Null
}
