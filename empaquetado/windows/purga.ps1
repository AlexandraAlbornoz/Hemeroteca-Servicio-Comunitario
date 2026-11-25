param([Parameter(Mandatory=$true)][string]$Directorio,[switch]$Prueba,[switch]$SinAsistente)
$ErrorActionPreference = 'Stop'

function Comprobar-Ruta([string]$ruta) {
    # Nunca atravesar un enlace, ni en la ruta ni en sus ancestros.
    $absoluta = [IO.Path]::GetFullPath($ruta)
    $actual = $absoluta
    while ($actual) {
        $item = Get-Item -LiteralPath $actual -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "La ruta contiene un enlace y requiere revisión manual: $actual"
        }
        $actual = [IO.Path]::GetDirectoryName($actual)
    }
    return $absoluta
}

function Eliminar-Arbol([string]$ruta,[string[]]$reservados=@()) {
    $ruta = Comprobar-Ruta $ruta
    if (-not (Test-Path -LiteralPath $ruta -PathType Container)) { return }
    foreach ($item in Get-ChildItem -LiteralPath $ruta -Force) {
        if ($item.Name -in $reservados) { continue }
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            if ($item.PSIsContainer) { [IO.Directory]::Delete($item.FullName,$false) }
            else { [IO.File]::Delete($item.FullName) }
        } elseif ($item.PSIsContainer) {
            Eliminar-Arbol $item.FullName
        } else {
            Remove-Item -LiteralPath $item.FullName -Force
        }
    }
    if (-not $reservados.Count) { Remove-Item -LiteralPath $ruta -Force }
}

function Eliminar-Archivo([string]$ruta) {
    $ruta = Comprobar-Ruta $ruta
    if (Test-Path -LiteralPath $ruta -PathType Leaf) { Remove-Item -LiteralPath $ruta -Force }
}

function Leer-Json([string]$ruta) {
    $ruta = Comprobar-Ruta $ruta
    if (Test-Path -LiteralPath $ruta -PathType Leaf) {
        Get-Content -LiteralPath $ruta -Raw -Encoding UTF8 | ConvertFrom-Json
    }
}

function Eliminar-Respaldos([string]$ruta) {
    $ruta = Comprobar-Ruta $ruta
    if (-not (Test-Path -LiteralPath $ruta -PathType Container)) { return }
    $firma = "HEMEROTECA-BACKUP$([char]1)$([char]13)$([char]10)"
    foreach ($archivo in Get-ChildItem -LiteralPath $ruta -File -Filter '*.hmbackup' -Force) {
        if ($archivo.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        $flujo = [IO.File]::OpenRead($archivo.FullName)
        try {
            $cabecera = New-Object byte[] $firma.Length
            $leidos = $flujo.Read($cabecera,0,$cabecera.Length)
        } finally { $flujo.Dispose() }
        if ($leidos -eq $firma.Length -and [Text.Encoding]::ASCII.GetString($cabecera) -ceq $firma) {
            Eliminar-Archivo $archivo.FullName
        }
    }
}

function Retirar-Firewall([string]$programa) {
    $firewall = Join-Path $PSScriptRoot 'firewall.ps1'
    $escritorio = [Environment]::GetFolderPath('DesktopDirectory')
    $argumentos = '-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File "{0}" -Modo Retirar -Programa "{1}" -Escritorio "{2}"' -f $firewall,$programa,$escritorio
    $proceso = Start-Process -FilePath "$PSHOME\powershell.exe" -Verb RunAs -WindowStyle Hidden -ArgumentList $argumentos -Wait -PassThru
    if ($proceso.ExitCode -ne 0) { throw 'Windows no pudo retirar las reglas del firewall. Vuelve a intentar la desinstalación.' }
}

$local = [Environment]::GetFolderPath('LocalApplicationData')
$programas = Join-Path $local 'Programs'
$almacen = Join-Path $local 'Hemeroteca-2.4'
$anterior = @('Hemeroteca','Hemeroteca-Correcciones','Hemeroteca-Perri','Hemeroteca-Perri-Maximo','Hemeroteca-2-4','Hemeroteca-Nucita')
$instalaciones = @('Hemeroteca','Hemeroteca-Perri','Hemeroteca-Perri-Maximo','Hemeroteca 2.4.0','Hemeroteca Nucita') | ForEach-Object { Join-Path $programas $_ }
$almacenes = @($almacen) + @($anterior | ForEach-Object { Join-Path $local $_ })

if ($Prueba) {
    if ((Split-Path -Leaf $Directorio) -notmatch '^Hemeroteca-Prueba-[a-f0-9]{32}$') { throw 'Destino de prueba incorrecto.' }
    $almacenes = @((Join-Path $Directorio 'perfil\Hemeroteca-2.4'),(Join-Path $Directorio 'perfil\Hemeroteca-Correcciones'))
    $instalaciones = @((Join-Path $Directorio 'perfil\Programs\Hemeroteca'))
} else {
    if ($Directorio -ine (Join-Path $programas 'Hemeroteca-2.4')) { throw 'Destino de desinstalación incorrecto.' }
    $paquetes = Join-Path $local 'Packages'
    foreach ($paquete in Get-ChildItem -LiteralPath $paquetes -Directory -Filter 'OpenAI.Codex_*' -ErrorAction SilentlyContinue) {
        $cache = Join-Path $paquete.FullName 'LocalCache\Local'
        foreach ($nombre in $anterior) {
            $carpeta = Join-Path $cache $nombre
            if (Test-Path -LiteralPath $carpeta -PathType Container) { $almacenes += $carpeta }
        }
    }
}
$null = Comprobar-Ruta $Directorio
$datos = @($almacenes | ForEach-Object { Join-Path $_ 'data' })
foreach ($base in @($instalaciones) + @($almacenes)) {
    $null = Comprobar-Ruta $base
    $ubicacion = Leer-Json (Join-Path $base 'ubicacion_datos.json')
    if ($ubicacion.directorio -and [IO.Path]::IsPathRooted([string]$ubicacion.directorio)) {
        $personalizada = Comprobar-Ruta $ubicacion.directorio
        if ($Prueba -and -not $personalizada.StartsWith($Directorio + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Los datos de prueba deben estar aislados.' }
        $datos += $personalizada
    }
}
$datos = @($datos | Sort-Object -Unique)
$carpetasRespaldos = foreach ($base in $datos) {
    $config = Leer-Json (Join-Path $base 'backup-settings.json')
    if ($config.directory -and [IO.Path]::IsPathRooted([string]$config.directory)) {
        $ruta = Comprobar-Ruta $config.directory
        if ($Prueba -and -not $ruta.StartsWith($Directorio + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Los respaldos de prueba deben estar aislados.' }
        $ruta
    }
    Join-Path $base 'respaldos'
    Join-Path $base 'backups'
}

if (-not $Prueba) {
    $programa = Join-Path $Directorio 'Hemeroteca.exe'
    $bases = @($Directorio) + @($instalaciones)
    foreach ($ejecucion in Get-Process -Name 'Hemeroteca','PerriMaximo','python','pythonw' -ErrorAction SilentlyContinue) {
        foreach ($base in $bases) {
            if ($ejecucion.Path -and $ejecucion.Path.StartsWith($base + '\',[StringComparison]::OrdinalIgnoreCase) -and $ejecucion.ProcessName -notin @('Hemeroteca','PerriMaximo')) {
                throw "Cierra la versión anterior antes de continuar: $($ejecucion.Path)"
            }
        }
    }
    foreach ($tarea in Get-ScheduledTask | Where-Object TaskName -match '^Hemeroteca-(?:Perri-Maximo-)?Respaldo-[a-f0-9]{16}$') {
        foreach ($accion in $tarea.Actions) {
            $exe = ([string]$accion.Execute).Trim('"')
            $propia = @($bases | Where-Object { $exe.StartsWith($_ + '\',[StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
            if (-not $propia -and $accion.Arguments -match '^--backup-worker --database "([^"]+)"') {
                $baseTarea = [IO.Path]::GetDirectoryName($Matches[1])
                $propia = $baseTarea -in $datos -and [IO.Path]::GetFileName($exe) -in @('Hemeroteca.exe','PerriMaximo.exe')
            }
            if (-not $propia) { continue }
            if ($tarea.State -eq 'Running') { Stop-ScheduledTask -InputObject $tarea }
            Unregister-ScheduledTask -InputObject $tarea -Confirm:$false
            break
        }
    }
    foreach ($base in $bases) {
        foreach ($nombre in @('Hemeroteca.exe','PerriMaximo.exe')) {
            $exe = Join-Path $base $nombre
            if (Test-Path -LiteralPath $exe -PathType Leaf) {
                try { $flujo = [IO.File]::Open($exe,'Open','ReadWrite','None'); $flujo.Dispose() }
                catch { throw "Cierra Hemeroteca antes de continuar: $exe" }
            }
        }
    }
    if (-not $SinAsistente) { Retirar-Firewall $programa }
}
foreach ($base in $datos) {
    $inventario = Join-Path $base 'archivos-generados'
    if (Test-Path -LiteralPath (Comprobar-Ruta $inventario) -PathType Container) {
        foreach ($entrada in Get-ChildItem -LiteralPath $inventario -File -Filter '*.json') {
            $registro = Leer-Json $entrada.FullName
            if ($registro.sha256 -notmatch '^[a-f0-9]{64}$' -or [IO.Path]::GetExtension($registro.ruta) -notin @('.pdf','.hmbackup')) { continue }
            $archivo = Comprobar-Ruta $registro.ruta
            if ($Prueba -and -not $archivo.StartsWith($Directorio + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Los archivos de prueba deben estar aislados.' }
            if ((Test-Path -LiteralPath $archivo -PathType Leaf) -and (Get-FileHash -LiteralPath $archivo -Algorithm SHA256).Hash -eq $registro.sha256) {
                Eliminar-Archivo $archivo
            }
        }
    }
}
foreach ($carpeta in $carpetasRespaldos | Sort-Object -Unique) { Eliminar-Respaldos $carpeta }
foreach ($base in $datos) {
    foreach ($nombre in @('hemeroteca.db','hemeroteca.db-wal','hemeroteca.db-shm','hemeroteca.db-journal','hemeroteca.db.maintenance.lock','hemeroteca.incoming.db','network.json','backup-settings.json','device.key')) {
        Eliminar-Archivo (Join-Path $base $nombre)
    }
    $respaldos = Comprobar-Ruta (Join-Path $base 'backups')
    if (Test-Path -LiteralPath $respaldos -PathType Container) {
        foreach ($copia in Get-ChildItem -LiteralPath $respaldos -File -Filter 'antes-de-traslado-*.db') {
            if ($copia.Name -match '^antes-de-traslado-[0-9]{8}-[0-9]{6}-[0-9]{6}\.db$') {
                Eliminar-Archivo $copia.FullName
            }
        }
    }
    Eliminar-Archivo (Join-Path $base 'tls\server.pem')
    Eliminar-Archivo (Join-Path $base 'tls\server.key')
    foreach ($subcarpeta in @('tls','archivos-generados','respaldos','backups')) {
        $ruta = Comprobar-Ruta (Join-Path $base $subcarpeta)
        if ((Test-Path -LiteralPath $ruta -PathType Container) -and @(Get-ChildItem -LiteralPath $ruta -Force).Count -eq 0) {
            Remove-Item -LiteralPath $ruta -Force
        }
    }
}
foreach ($ruta in @($almacenes) + @($instalaciones)) { Eliminar-Arbol $ruta }
if (-not $Prueba) {
    $menu = [Environment]::GetFolderPath('Programs')
    $escritorio = [Environment]::GetFolderPath('DesktopDirectory')
    $shell = New-Object -ComObject WScript.Shell
    $nombresMenu = $anterior + @('Hemeroteca 2.4.0','Hemeroteca Nucita','Perri Maximo')
    if ($SinAsistente) { $nombresMenu += 'Hemeroteca 2.4' }
    $carpetas = @($escritorio,$menu) + @($nombresMenu | ForEach-Object { Join-Path $menu $_ })
    $destinos = @($instalaciones)
    if ($SinAsistente) { $destinos += $Directorio }
    foreach ($carpeta in $carpetas | Sort-Object -Unique) {
        if (-not (Test-Path -LiteralPath (Comprobar-Ruta $carpeta) -PathType Container)) { continue }
        foreach ($acceso in Get-ChildItem -LiteralPath $carpeta -File -Filter '*.lnk') {
            $destino = $shell.CreateShortcut($acceso.FullName).TargetPath
            if (@($destinos | Where-Object { $destino -ieq $_ -or $destino.StartsWith($_ + '\',[StringComparison]::OrdinalIgnoreCase) }).Count) {
                Eliminar-Archivo $acceso.FullName
            }
        }
        if ((Split-Path -Parent $carpeta) -eq $menu -and @(Get-ChildItem -LiteralPath $carpeta -Force).Count -eq 0) {
            Remove-Item -LiteralPath $carpeta
        }
    }
    $claves = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall'
    foreach ($clave in Get-ChildItem -LiteralPath $claves -ErrorAction SilentlyContinue) {
        $info = Get-ItemProperty -LiteralPath $clave.PSPath
        if ($clave.PSChildName -in @('HemerotecaHemeroteca','HemerotecaPerriMaximo','Hemeroteca24-0') -or ($SinAsistente -and $clave.PSChildName -eq 'Hemeroteca24') -or $info.InstallLocation -in $destinos) {
            Remove-Item -LiteralPath $clave.PSPath -Force
        }
    }
}
if ($SinAsistente) {
    Eliminar-Arbol $Directorio
    if (-not $Prueba) { Retirar-Firewall $programa }
} else {
    Eliminar-Arbol $Directorio @('Desinstalar_Hemeroteca.exe','.Hemeroteca-instalacion.json')
}
