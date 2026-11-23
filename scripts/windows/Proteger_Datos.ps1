param(
    [Parameter(Mandatory=$true)][string]$DataDirectory,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$target = [IO.Path]::GetFullPath($DataDirectory).TrimEnd('\')
$root = [IO.Path]::GetPathRoot($target).TrimEnd('\')
$profilePath = [Environment]::GetFolderPath('UserProfile').TrimEnd('\')
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..')).TrimEnd('\')
if ($target -eq $root -or $target -eq $profilePath -or $target -eq $repository -or $target.StartsWith('\\')) {
    throw 'Seleccione solo la carpeta de datos, nunca una unidad, perfil, repositorio o ruta de red.'
}
# No seguir enlaces ni puntos de unión; comprobar todos los padres antes de crear.
$ancestor = $target
while ($ancestor) {
    if (Test-Path -LiteralPath $ancestor) {
        $item = Get-Item -LiteralPath $ancestor -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'No se admiten enlaces ni puntos de unión.' }
    }
    $ancestor = Split-Path -Parent $ancestor
}
if ((Test-Path -LiteralPath $target) -and -not (Test-Path -LiteralPath $target -PathType Container)) {
    throw 'La ruta debe ser una carpeta.'
}
$userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$systemSid = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
if (-not $Apply) {
    Write-Output ('Vista previa: ' + $target)
    Write-Output ('Al aplicar, solo tendrán acceso la cuenta actual (' + $userSid.Value + ') y SYSTEM.')
    Write-Output 'Cierre Hemeroteca y repita con -Apply para proteger la carpeta y su contenido.'
    exit 0
}
# Importar el módulo de este intérprete, sin resolver otro módulo homónimo en PSModulePath.
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
if (-not (Test-Path -LiteralPath $target)) { New-Item -ItemType Directory -Path $target | Out-Null }
$children = @(Get-ChildItem -LiteralPath $target -Recurse -Force)
foreach ($item in $children) {
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Hay un enlace en la carpeta; no se modificaron permisos.' }
}
foreach ($item in @((Get-Item -LiteralPath $target)) + $children) {
    if ($item.PSIsContainer) {
        $acl = [Security.AccessControl.DirectorySecurity]::new()
        $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    } else {
        $acl = [Security.AccessControl.FileSecurity]::new()
        $inheritance = [Security.AccessControl.InheritanceFlags]::None
    }
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @($userSid, $systemSid)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', $inheritance, 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $item.FullName -AclObject $acl
}
Write-Output ('Permisos restringidos a cuenta actual y SYSTEM: ' + $target)
