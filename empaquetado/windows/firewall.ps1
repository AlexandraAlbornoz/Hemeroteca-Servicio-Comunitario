param(
    [ValidateSet('Configurar','Retirar')][string]$Modo,
    [Parameter(Mandatory=$true)][string]$Programa,
    [string]$Escritorio
)
$ErrorActionPreference = 'Stop'
try {
    $Programa = [IO.Path]::GetFullPath($Programa)
    if ([IO.Path]::GetFileName($Programa) -ne 'Hemeroteca.exe') { throw 'Ejecutable inválido.' }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $id = ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Programa.ToLowerInvariant())))).Replace('-','').Substring(0,24) }
    finally { $sha.Dispose() }
    $tcp = "Hemeroteca24-$id-TCP"
    $udp = "Hemeroteca24-$id-UDP"
    if ($Modo -eq 'Configurar') {
        if (-not (Test-Path -LiteralPath $Programa -PathType Leaf)) { throw 'Instala Hemeroteca 2.4.0 primero.' }
        if (-not (Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Private')) { throw 'Selecciona el perfil privado para tu red local.' }
    }
    $reglas = @(Get-NetFirewallRule -PolicyStore PersistentStore)
    $raiz = Split-Path -Parent (Split-Path -Parent $Programa)
    $antiguos = @('Hemeroteca','Hemeroteca-Perri','Hemeroteca-Perri-Maximo','Hemeroteca 2.4.0','Hemeroteca Nucita') | ForEach-Object { (Join-Path $raiz $_).TrimEnd('\') + '\' }
    $rutaAnterior = if ($Escritorio) { Join-Path ([IO.Path]::GetFullPath($Escritorio)) 'hemeroteca correcciones nuevas\hemeroteca.exe' }
    foreach ($regla in $reglas) {
        if ($regla.Name -in @($tcp,$udp)) {
            $filtro = $regla | Get-NetFirewallApplicationFilter
            if ($filtro.Program -ine $Programa) { throw 'Existe una regla con el mismo identificador y otro ejecutable.' }
            $regla | Remove-NetFirewallRule
        } elseif ($Modo -eq 'Retirar' -and $regla.Name -match '^(?:Hemeroteca-(?:(?:Perri-Maximo-)?(?:TLS|WiFi)-[0-9]+|[a-f0-9]{16}-(?:TLS|WiFi))|(?:TCP|UDP) Query User\{)') {
            $aplicacion = [Environment]::ExpandEnvironmentVariables([string]($regla | Get-NetFirewallApplicationFilter).Program)
            if ($aplicacion -ieq $Programa -or ($rutaAnterior -and $aplicacion -ieq $rutaAnterior)) { $regla | Remove-NetFirewallRule; continue }
            foreach ($prefijo in $antiguos) {
                if ($aplicacion.StartsWith($prefijo,[StringComparison]::OrdinalIgnoreCase)) { $regla | Remove-NetFirewallRule; break }
            }
        }
    }
    if ($Modo -eq 'Configurar') {
        $comun = @{Direction='Inbound'; Action='Allow'; Program=$Programa; Profile='Private'; RemoteAddress='LocalSubnet'; EdgeTraversalPolicy='Block'; PolicyStore='PersistentStore'}
        New-NetFirewallRule @comun -Name $tcp -DisplayName 'Hemeroteca 2.4 - HTTPS local' -Protocol TCP -LocalPort 8765,8767 | Out-Null
        New-NetFirewallRule @comun -Name $udp -DisplayName 'Hemeroteca 2.4 - detección local' -Protocol UDP -LocalPort 8766 | Out-Null
    }
    exit 0
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    [void][Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Firewall de Hemeroteca')
    exit 1
}
