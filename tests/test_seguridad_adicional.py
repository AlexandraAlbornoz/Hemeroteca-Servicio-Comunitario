"""Regresiones de contraseñas largas y permisos de datos en Windows."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from hemeroteca.config.settings import SECURITY_QUESTIONS
from hemeroteca.services.container import create_services
from hemeroteca.utils.security import password_hash, password_matches


class PruebasContrasenasLargas(unittest.TestCase):
    """Verifica que ampliar el máximo no invalide hashes o cuentas existentes."""

    def test_registro_y_autenticacion_con_128_caracteres(self):
        """Una cuenta nueva conserva y verifica la contraseña completa sin truncarla."""
        services = create_services(':memory:')
        try:
            password = 'Aa1#' + 'z' * 124  # pragma: allowlist secret -- contraseña sintética para probar el límite
            questions = tuple(zip(SECURITY_QUESTIONS[:3], ('Luna', 'María', 'Caracas')))
            services.auth.create_master('Persona Ficticia', 'V-12345678', password, questions)
            account = services.auth.authenticate('V-12345678', password)
            self.assertTrue(password_matches(password, account['password']))
            self.assertFalse(password_matches(password[:-1] + 'x', account['password']))
        finally:
            services.close()

    def test_hash_heredado_sigue_siendo_valido(self):
        """Mantiene el formato sal:hash utilizado por las cuentas existentes."""
        saved = password_hash('Abcd#123')
        self.assertEqual(len(saved.split(':')), 2)
        self.assertTrue(password_matches('Abcd#123', saved))

    def test_entrada_excesiva_se_rechaza_antes_de_derivar(self):
        """Una entrada desproporcionada no dispara el cálculo PBKDF2."""
        with patch('hemeroteca.utils.security.hashlib.pbkdf2_hmac') as derive:
            self.assertFalse(password_matches('A' * 129, '00:00'))
            derive.assert_not_called()


@unittest.skipUnless(os.name == 'nt', 'ACL de Windows')
class PruebasPermisosWindows(unittest.TestCase):
    """Aplica las restricciones exclusivamente a archivos temporales ficticios."""

    def test_acl_restringida_e_heredada_por_nuevos_archivos(self):
        """Solo la cuenta actual y SYSTEM conservan permisos explícitos de acceso."""
        script = Path(__file__).resolve().parents[1] / 'scripts/windows/Proteger_Datos.ps1'
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'datos'
            folder.mkdir()
            (folder / 'ficticio.txt').write_text('datos sintéticos', encoding='utf-8')
            result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script),
                                     '-DataDirectory', str(folder), '-Apply'],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            (folder / 'nuevo.txt').write_text('herencia', encoding='utf-8')
            command = '''Import-Module (Join-Path $PSHOME 'Modules\\Microsoft.PowerShell.Security\\Microsoft.PowerShell.Security.psd1') -ErrorAction Stop
$allowed = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, 'S-1-5-18')
$ok = $true
foreach ($path in @($env:HEMEROTECA_ACL_TEST_PATH, (Join-Path $env:HEMEROTECA_ACL_TEST_PATH 'ficticio.txt'), (Join-Path $env:HEMEROTECA_ACL_TEST_PATH 'nuevo.txt'))) {
    $acl = Get-Acl -LiteralPath $path
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) { $ok = $false }
    foreach ($rule in $rules) {
        if ($rule.IdentityReference.Value -notin $allowed -or $rule.AccessControlType -ne 'Allow') { $ok = $false }
    }
}
$ok | ConvertTo-Json'''
            result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                                    env=dict(os.environ, HEMEROTECA_ACL_TEST_PATH=str(folder)),
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout))

    def test_rechaza_raiz_del_repositorio(self):
        """Impide aplicar permisos de datos a todo el código fuente."""
        root = Path(__file__).resolve().parents[1]
        script = root / 'scripts/windows/Proteger_Datos.ps1'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(script),
                                 '-DataDirectory', str(root)],
                                capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
