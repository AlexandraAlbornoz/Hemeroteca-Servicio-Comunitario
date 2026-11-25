param(
    [ValidateSet('Instalar','Desinstalar')][string]$Modo,
    [string]$Paquete,
    [Parameter(Mandatory=$true)][string]$Directorio,
    [Parameter(Mandatory=$true)][string]$Informe,
    [switch]$Escritorio,
    [switch]$Prueba
)
$ErrorActionPreference = 'Stop'

function Guardar-Estado([int]$porcentaje, [string]$mensaje, [bool]$terminado=$false, [bool]$correcto=$true) {
    # El asistente lee este archivo; nunca se escriben credenciales o datos de cuentas.
    $estado = @{porcentaje=$porcentaje; mensaje=$mensaje; terminado=$terminado; correcto=$correcto}
    $temporal = $Informe + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temporal, ($estado | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $temporal -Destination $Informe -Force
}

function Ruta-Segura([string]$raiz, [string]$relativa) {
    # Comprueba todos los destinos antes de copiar o quitar un archivo.
    $absoluta = [IO.Path]::GetFullPath((Join-Path $raiz $relativa))
    if (-not $absoluta.StartsWith($raiz.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'El paquete contiene una ruta fuera de la carpeta del programa.'
    }
    return $absoluta
}

function Crear-Acceso([string]$ruta, [string]$programa, [string]$icono) {
    # Crea accesos de Windows con el periódico y sin abrir una consola.
    $acceso = (New-Object -ComObject WScript.Shell).CreateShortcut($ruta)
    $acceso.TargetPath = $programa
    $acceso.WorkingDirectory = $Directorio
    $acceso.IconLocation = $icono
    $acceso.Description = 'Hemeroteca - Hemeroteca'
    $acceso.Save()
}

function Calcular-Huella([string]$ruta) {
    # No depende del módulo Get-FileHash, que varía entre hosts de PowerShell.
    $algoritmo = [Security.Cryptography.SHA256]::Create()
    $flujo = [IO.File]::OpenRead($ruta)
    try { return ([BitConverter]::ToString($algoritmo.ComputeHash($flujo))).Replace('-','').ToLowerInvariant() }
    finally { $flujo.Dispose(); $algoritmo.Dispose() }
}

try {
    $Directorio = [IO.Path]::GetFullPath($Directorio)
    $normal = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Hemeroteca-2.4.2-solo-consulta'
    if (-not $Prueba -and $Directorio -ine $normal) { throw 'La carpeta de instalación no es válida.' }
    if ($Prueba -and (Split-Path -Leaf $Directorio) -notmatch '^Hemeroteca-Prueba-[a-f0-9]{32}$') {
        throw 'La carpeta de prueba debe ser exclusiva y tener un identificador aleatorio.'
    }
    if ((Test-Path -LiteralPath $Directorio) -and ((Get-Item -LiteralPath $Directorio -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'La carpeta de instalación no puede ser un enlace.'
    }
    if ($Modo -eq 'Instalar' -and (Test-Path -LiteralPath $Directorio) -and
        @(Get-ChildItem -LiteralPath $Directorio -Force).Count -gt 0 -and
        -not (Test-Path -LiteralPath (Join-Path $Directorio '.Hemeroteca-instalacion.json') -PathType Leaf)) {
        throw 'La carpeta de instalación ya contiene archivos de otra instalación.'
    }
    $ejecutable = Join-Path $Directorio 'Hemeroteca.exe'
    if (Test-Path -LiteralPath $ejecutable) {
        # Windows puede seguir liberando el ejecutable después de cerrar su ventana.
        # Espera brevemente, pero nunca sustituye o elimina un archivo aún ocupado.
        $limiteLiberacion = [DateTime]::UtcNow.AddSeconds(10)
        $archivoLibre = $false
        do {
            try {
                $comprobacion = [IO.File]::Open($ejecutable, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
                $comprobacion.Close()
                $archivoLibre = $true
            } catch {
                if ([DateTime]::UtcNow -ge $limiteLiberacion) {
                    throw 'Cierra Hemeroteca, espera unos segundos y vuelve a intentarlo. Tus datos se conservan.'
                }
                Start-Sleep -Milliseconds 250
            }
        } while (-not $archivoLibre)
    }
    $menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Hemeroteca 2.4.2 Solo consulta'
    $clave = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Hemeroteca242SoloConsulta'
    $marcador = Join-Path $Directorio '.Hemeroteca-instalacion.json'
    if ($Modo -eq 'Instalar') {
        Guardar-Estado 5 'Comprobando el paquete...'
        $Paquete = [IO.Path]::GetFullPath($Paquete)
        $contenido = Get-Content -LiteralPath (Join-Path $Paquete 'contenido.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($archivo in $contenido.archivos) {
            $origen = Ruta-Segura $Paquete $archivo.ruta
            if ((Calcular-Huella $origen) -ne $archivo.sha256) {
                throw 'El instalador está incompleto o alterado. Utiliza una copia nueva.'
            }
        }
        New-Item -ItemType Directory -Path $Directorio -Force | Out-Null
        $cantidad = @($contenido.archivos).Count
        $indice = 0
        foreach ($archivo in $contenido.archivos) {
            $destino = Ruta-Segura $Directorio $archivo.ruta
            $carpeta = Split-Path -Parent $destino
            if (-not (Test-Path -LiteralPath $carpeta)) { New-Item -ItemType Directory -Path $carpeta -Force | Out-Null }
            Copy-Item -LiteralPath (Ruta-Segura $Paquete $archivo.ruta) -Destination $destino -Force
            $indice++
            if ($indice % 15 -eq 0) { Guardar-Estado ([int](10 + 75 * $indice / $cantidad)) 'Instalando el programa y sus recursos...' }
        }
        $registro = @{identificador='Hemeroteca-2.4.2-solo-consulta'; version='2.4.2'; prueba=[bool]$Prueba; archivos=@($contenido.archivos.ruta)}
        [IO.File]::WriteAllText($marcador, ($registro | ConvertTo-Json -Depth 5), (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $Directorio '.Hemeroteca-instalacion'), 'Hemeroteca-2.4.2-solo-consulta')
        Guardar-Estado 90 'Preparando los accesos directos...'
        if (-not $Prueba) {
            New-Item -ItemType Directory -Path $menu -Force | Out-Null
            $icono = Join-Path $Directorio 'assets\hemeroteca_periodico.ico'
            Crear-Acceso (Join-Path $menu 'Hemeroteca 2.4.2 Solo consulta.lnk') $ejecutable $icono
            Crear-Acceso (Join-Path $menu 'Desinstalar Hemeroteca.lnk') (Join-Path $Directorio 'Desinstalar_Hemeroteca.exe') $icono
            if ($Escritorio) { Crear-Acceso (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Hemeroteca 2.4.2 Solo consulta.lnk') $ejecutable $icono }
            New-Item -Path $clave -Force | Out-Null
            $propiedades = @{DisplayName='Hemeroteca 2.4.2 Solo consulta'; DisplayVersion='2.4.2'; Publisher='Hemeroteca'; InstallLocation=$Directorio; DisplayIcon=($ejecutable + ',0'); UninstallString=('"' + (Join-Path $Directorio 'Desinstalar_Hemeroteca.exe') + '"')}
            foreach ($nombre in $propiedades.Keys) { New-ItemProperty -Path $clave -Name $nombre -Value $propiedades[$nombre] -PropertyType String -Force | Out-Null }
            New-ItemProperty -Path $clave -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
            New-ItemProperty -Path $clave -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null
        }
        Guardar-Estado 100 'Hemeroteca está listo.' $true $true
    } else {
        Guardar-Estado 5 'Comprobando la instalación...'
        $registro = Get-Content -LiteralPath $marcador -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($registro.identificador -ne 'Hemeroteca-2.4.2-solo-consulta') { throw 'No se encontró una instalación válida. No se quitaron archivos.' }
        Guardar-Estado 20 'Retirando esta copia de Hemeroteca...'
        foreach ($relativa in $registro.archivos) {
            $archivo = Ruta-Segura $Directorio $relativa
            if ($archivo -ieq (Join-Path $Directorio 'Desinstalar_Hemeroteca.exe')) { continue }
            if (Test-Path -LiteralPath $archivo -PathType Leaf) { Remove-Item -LiteralPath $archivo -Force }
        }
        $carpetas = Get-ChildItem -LiteralPath $Directorio -Directory -Recurse | Sort-Object { $_.FullName.Length } -Descending
        foreach ($carpeta in $carpetas) {
            if (@(Get-ChildItem -LiteralPath $carpeta.FullName -Force).Count -eq 0) { Remove-Item -LiteralPath $carpeta.FullName }
        }
        if (-not $Prueba) {
            $accesos = @(
                (Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) 'Hemeroteca 2.4.2 Solo consulta.lnk'),
                (Join-Path $menu 'Hemeroteca 2.4.2 Solo consulta.lnk'),
                (Join-Path $menu 'Desinstalar Hemeroteca.lnk')
            )
            foreach ($acceso in $accesos) {
                if (Test-Path -LiteralPath $acceso) { Remove-Item -LiteralPath $acceso -Force }
            }
            if ((Test-Path -LiteralPath $menu) -and @(Get-ChildItem -LiteralPath $menu -Force).Count -eq 0) {
                Remove-Item -LiteralPath $menu
            }
            if (Test-Path -LiteralPath $clave) { Remove-Item -LiteralPath $clave -Force }
        }
        Guardar-Estado 100 'Programa retirado. Los datos se conservan. Cierra el asistente para retirar el desinstalador.' $true $true
    }
} catch {
    Guardar-Estado 0 $_.Exception.Message $true $false
    exit 1
}
