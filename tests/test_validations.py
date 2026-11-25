"""Pruebas de validación con SQLite en memoria; no utilizan data/hemeroteca.db.

Ejecutar desde la raíz: ./.venv/bin/python -m unittest discover -s tests -v
"""

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from config.settings import NATIONAL, REGIONAL, ROLES, SECURITY_QUESTIONS
from main import create_services
from services.access_service import AccessDenied
from utils.dates import parse_filter_date
from utils.security import normalize_security_answer, password_matches, prepare_security_questions
from ui.login_view import LoginView


MASTER_PASSWORD = "Maestro!2026"
USER_PASSWORD = "Usuario!2026"
ADMIN_PASSWORD = "Admin!2026"
NEW_PASSWORD = "Nueva!2026"
ANSWERS = ("Luna", "María", "Pecas")
QUESTIONS = tuple(zip(SECURITY_QUESTIONS, ANSWERS))


class ValidationTests(unittest.TestCase):
    """Comprueba validaciones de negocio y formularios sobre copias independientes de una base sintética."""
    @classmethod
    def setUpClass(cls):
        """Prepara una base semilla con maestro, usuario y administrador y configura sus credenciales ficticias."""
        cls.seed = create_services(":memory:")
        cls.master_result = cls.seed.auth.create_master("Maestro de prueba", "V-10000001", MASTER_PASSWORD, QUESTIONS)
        cls.master_id = cls.seed.auth.authenticate("V-10000001", MASTER_PASSWORD, ROLES[0])["id"]
        cls.user_result = cls.seed.users.create_user("Usuario de prueba", "V-10000002", USER_PASSWORD, security_answers=ANSWERS)
        master = cls.seed.auth.authenticate("V-10000001", MASTER_PASSWORD, ROLES[0])
        cls.admin_result = cls.seed.users.create_user("Admin de prueba", "E-10000003", "Tempora!2026", ROLES[1], actor=master)
        cls.user_id = cls.user_result.user_id
        cls.admin_id = cls.admin_result.user_id
        admin = cls.seed.auth.authenticate("E-10000003", "Tempora!2026", ROLES[1])
        admin = cls.seed.auth.change_password(admin, "Tempora!2026", ADMIN_PASSWORD)
        cls.seed.recovery.configure_questions(admin, ADMIN_PASSWORD, QUESTIONS)

    @classmethod
    def tearDownClass(cls):
        """Cierra la conexión de la base semilla al terminar el conjunto de pruebas."""
        cls.seed.close()

    def setUp(self):
        """Copia la semilla a una base en memoria y recupera las cuentas utilizadas por cada prueba."""
        self.s = create_services(":memory:")
        self.seed.connection.backup(self.s.connection)
        self.master = self.row(self.master_id)
        self.user = self.row(self.user_id)
        self.admin = self.row(self.admin_id)

    def tearDown(self):
        """Cierra los servicios y la base aislada de la prueba actual."""
        self.s.close()

    def row(self, user_id):
        """Obtiene una cuenta de la base de prueba por su identificador."""
        return self.s.connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def snapshot(self):
        'Copia un estado consistente de SQLite a una representación transportable.'
        return {table: [tuple(row) for row in self.s.connection.execute(f"SELECT * FROM {table} ORDER BY rowid")]
                for table in ("users", "user_security", "issues", "absent_dates", "grants", "requests")}

    def rejects(self, error, function, *args, **kwargs):
        """Comprueba que la operación lance el error esperado y no cambie la instantánea de datos."""
        before = self.snapshot()
        with self.assertRaises(error):
            function(*args, **kwargs)
        self.assertEqual(before, self.snapshot(), "Una operación rechazada cambió datos")

    def issue_values(self, **changes):
        """Construye una tupla válida de ejemplar y aplica sustituciones puntuales para cada caso de validación."""
        values = dict(title=NATIONAL[0], kind="Nacional", edition="Matutina", year=2020,
                      month=4, day=15, number="100", shelf="1", drawer="2", status="Disponible")
        values.update(changes)
        return tuple(values.values())

    def save_issue(self, **changes):
        """Guarda un ejemplar ficticio mediante el servicio y devuelve el identificador recién creado."""
        self.s.periodicos.save_record(self.master, self.issue_values(**changes))
        return self.s.connection.execute("SELECT max(id) FROM issues").fetchone()[0]

    def absent_values(self, **changes):
        """Construye una tupla válida de fecha sin publicación con los cambios indicados por la prueba."""
        values = dict(title=NATIONAL[0], kind="Nacional", year=2020, month=4, day=15, note="Prueba")
        values.update(changes)
        return tuple(values.values())

    def test_01_fresh_database_requires_master_and_has_no_accounts(self):
        'Verifica la validación y conservación de datos del caso test_01_fresh_database_requires_master_and_has_no_accounts.'
        fresh = create_services(":memory:")
        try:
            self.assertTrue(fresh.auth.needs_setup())
            self.assertEqual(fresh.connection.execute("SELECT count(*) FROM users").fetchone()[0], 0)
        finally:
            fresh.close()

    def test_02_master_cannot_be_created_twice(self):
        'Verifica la validación y conservación de datos del caso test_02_master_cannot_be_created_twice.'
        self.rejects(ValueError, self.s.auth.create_master, "Otro maestro", "V-20000002", NEW_PASSWORD, QUESTIONS)

    def test_03_setup_rejects_empty_fields_and_short_password(self):
        'Verifica la validación y conservación de datos del caso test_03_setup_rejects_empty_fields_and_short_password.'
        for name, identity, password in ((" ", "x", NEW_PASSWORD), ("Nombre Prueba", " ", NEW_PASSWORD), ("Nombre Prueba", "x", "1234567")):
            with self.subTest(name=name, identity=identity):
                self.rejects(ValueError, self.s.auth.create_master, name, identity, password, QUESTIONS)

    def test_04_signup_requires_three_answers(self):
        'Verifica la validación y conservación de datos del caso test_04_signup_requires_three_answers.'
        for answers in (None, (), ("Una", "Dos"), ("Una", "Dos", ""), ("Una", " ", "Tres"), ("x" * 201, "Dos", "Tres")):
            with self.subTest(answers=answers):
                self.rejects(ValueError, self.s.users.create_user, "Persona Prueba", "V-20000001", NEW_PASSWORD, security_answers=answers)

    def test_05_signup_rejects_empty_fields_and_short_password(self):
        'Verifica la validación y conservación de datos del caso test_05_signup_rejects_empty_fields_and_short_password.'
        for name, identity, password in ((" ", "V-20000001", NEW_PASSWORD), ("Persona Prueba", " ", NEW_PASSWORD), ("Persona Prueba", "V-20000001", "1234567")):
            with self.subTest(name=name, identity=identity):
                self.rejects(ValueError, self.s.users.create_user, name, identity, password, security_answers=ANSWERS)

    def test_06_signup_rejects_duplicate_identity_case_insensitively(self):
        'Verifica la validación y conservación de datos del caso test_06_signup_rejects_duplicate_identity_case_insensitively.'
        for identity in ("V-10000002",):
            self.rejects(sqlite3.IntegrityError, self.s.users.create_user, "Otra persona", identity, NEW_PASSWORD, security_answers=ANSWERS)

    def test_07_signup_cannot_choose_an_administrator_role(self):
        'Verifica la validación y conservación de datos del caso test_07_signup_cannot_choose_an_administrator_role.'
        for role in (ROLES[0], "Perfil inventado"):
            self.rejects(AccessDenied, self.s.users.create_user, "Persona Prueba", "V-20000001", NEW_PASSWORD, role, security_answers=ANSWERS)

    def test_08_signup_is_blocked_until_master_exists(self):
        'Verifica la validación y conservación de datos del caso test_08_signup_is_blocked_until_master_exists.'
        fresh = create_services(":memory:")
        try:
            with self.assertRaises(ValueError):
                fresh.users.create_user("Persona Prueba", "V-20000001", NEW_PASSWORD, security_answers=ANSWERS)
        finally:
            fresh.close()

    def test_09_valid_signup_trims_fields_and_hashes_credentials(self):
        'Verifica la validación y conservación de datos del caso test_09_valid_signup_trims_fields_and_hashes_credentials.'
        user_id = self.s.users.create_user(" Persona Prueba ", "V-20000001", "Valida#2026", security_answers=ANSWERS).user_id
        user = self.row(user_id)
        self.assertEqual((user["name"], user["identity"]), ("Persona Prueba", "V-20000001"))
        self.assertTrue(password_matches("Valida#2026", user["password"]))
        self.assertNotEqual(user["password"], "12345678")
        self.assertFalse(self.s.recovery.needs_configuration(user))

    def test_10_security_questions_reject_invalid_count_lengths_and_duplicates(self):
        'Verifica la validación y conservación de datos del caso test_10_security_questions_reject_invalid_count_lengths_and_duplicates.'
        invalid = (None, (), QUESTIONS[:2], (("Corta", "Una"),) + QUESTIONS[1:],
                   (("x" * 201, "Una"),) + QUESTIONS[1:],
                   ((SECURITY_QUESTIONS[0], ""),) + QUESTIONS[1:],
                   (QUESTIONS[0], (SECURITY_QUESTIONS[0].upper(), "Otra"), QUESTIONS[2]))
        for questions in invalid:
            with self.subTest(questions=questions):
                with self.assertRaises(ValueError):
                    prepare_security_questions(questions)

    def test_11_security_answers_accept_50_characters_and_preserve_accents(self):
        'Verifica la validación y conservación de datos del caso test_11_security_answers_accept_50_characters_and_preserve_accents.'
        values = prepare_security_questions(((SECURITY_QUESTIONS[0], "x" * 50),) + QUESTIONS[1:])
        self.assertTrue(password_matches("x" * 50, values[1]))
        self.assertEqual(normalize_security_answer("  MARÍA  de   la Luz "), "maría de la luz")
        self.assertNotEqual(normalize_security_answer("María"), normalize_security_answer("Maria"))

    def test_12_login_accepts_correct_credentials_and_case_insensitive_identity(self):
        'Verifica la validación y conservación de datos del caso test_12_login_accepts_correct_credentials_and_case_insensitive_identity.'
        account = self.s.auth.authenticate(" v-10000002 ", USER_PASSWORD, ROLES[2])
        self.assertEqual(account["id"], self.user_id)

    def test_13_login_rejects_wrong_password_unknown_user_empty_fields_and_sql_injection(self):
        'Verifica la validación y conservación de datos del caso test_13_login_rejects_wrong_password_unknown_user_empty_fields_and_sql_injection.'
        for identity, password in (("V-10000002", "Incorrecta"), ("V-99999999", USER_PASSWORD),
                                   ("", ""), ("' OR 1=1 --", USER_PASSWORD)):
            with self.subTest(identity=identity):
                self.rejects(ValueError, self.s.auth.authenticate, identity, password, ROLES[2])

    def test_14_login_rejects_wrong_role(self):
        'Verifica la validación y conservación de datos del caso test_14_login_rejects_wrong_role.'
        self.rejects(AccessDenied, self.s.auth.authenticate, "V-10000002", USER_PASSWORD, ROLES[0])

    def test_15_inactive_user_cannot_login_or_use_existing_session(self):
        'Verifica la validación y conservación de datos del caso test_15_inactive_user_cannot_login_or_use_existing_session.'
        self.s.users.set_user_active(self.master, self.user_id, False)
        self.rejects(AccessDenied, self.s.auth.authenticate, "V-10000002", USER_PASSWORD, ROLES[2])
        self.rejects(AccessDenied, self.s.periodicos.consult_issues, self.user, 2020, 1, 1)

    def test_16_unauthenticated_and_forged_role_cannot_manage_accounts(self):
        'Verifica la validación y conservación de datos del caso test_16_unauthenticated_and_forged_role_cannot_manage_accounts.'
        forged = dict(self.user)
        forged["role"] = ROLES[0]
        for actor in (None, self.user, self.admin, forged):
            self.rejects(AccessDenied, self.s.users.set_user_active, actor, self.user_id, False)

    def test_17_password_change_rejects_short_same_and_wrong_current_password(self):
        'Verifica la validación y conservación de datos del caso test_17_password_change_rejects_short_same_and_wrong_current_password.'
        for current, new in ((USER_PASSWORD, "1234567"), (USER_PASSWORD, USER_PASSWORD), ("Incorrecta", NEW_PASSWORD)):
            self.rejects(ValueError, self.s.auth.change_password, self.user, current, new)

    def test_18_password_change_invalidates_old_password_and_session(self):
        'Verifica la validación y conservación de datos del caso test_18_password_change_invalidates_old_password_and_session.'
        updated = self.s.auth.change_password(self.user, USER_PASSWORD, NEW_PASSWORD)
        self.assertNotEqual(updated["password_version"], self.user["password_version"])
        self.rejects(AccessDenied, self.s.periodicos.consult_issues, self.user, 2020, 1, 1)
        self.rejects(AccessDenied, self.s.auth.authenticate, "V-10000002", USER_PASSWORD, ROLES[2])
        self.assertEqual(self.s.auth.authenticate("V-10000002", NEW_PASSWORD, ROLES[2])["id"], self.user_id)

    def test_19_only_master_can_reset_another_password(self):
        'Verifica la validación y conservación de datos del caso test_19_only_master_can_reset_another_password.'
        for actor in (None, self.user, self.admin):
            self.rejects(AccessDenied, self.s.users.reset_password, actor, self.user_id, MASTER_PASSWORD, NEW_PASSWORD)
        self.rejects(AccessDenied, self.s.users.reset_password, self.master, self.user_id, "Incorrecta", NEW_PASSWORD)

    def test_20_master_reset_rejects_short_password_and_missing_user(self):
        'Verifica la validación y conservación de datos del caso test_20_master_reset_rejects_short_password_and_missing_user.'
        self.rejects(ValueError, self.s.users.reset_password, self.master, self.user_id, MASTER_PASSWORD, "1234567")
        self.rejects(ValueError, self.s.users.reset_password, self.master, 99999, MASTER_PASSWORD, NEW_PASSWORD)

    def test_21_reset_requires_a_personal_password_before_catalog_access(self):
        'Verifica la validación y conservación de datos del caso test_21_reset_requires_a_personal_password_before_catalog_access.'
        self.s.users.reset_password(self.master, self.user_id, MASTER_PASSWORD, NEW_PASSWORD)
        temporary = self.s.auth.authenticate("V-10000002", NEW_PASSWORD, ROLES[2])
        self.assertTrue(temporary["must_change_password"])
        self.rejects(AccessDenied, self.s.periodicos.consult_issues, temporary, 2020, 1, 1)
        updated = self.s.auth.change_password(temporary, NEW_PASSWORD, USER_PASSWORD)
        self.assertFalse(updated["must_change_password"])
        self.s.periodicos.consult_issues(updated, 2020, 1, 1)

    def test_22_master_created_account_requires_password_change_and_own_answers(self):
        'Verifica la validación y conservación de datos del caso test_22_master_created_account_requires_password_change_and_own_answers.'
        user_id = self.s.users.create_user("Cuenta administrada", "E-20000003", NEW_PASSWORD, actor=self.master).user_id
        actor = self.s.auth.authenticate("E-20000003", NEW_PASSWORD, ROLES[2])
        self.assertTrue(actor["must_change_password"])
        actor = self.s.auth.change_password(actor, NEW_PASSWORD, USER_PASSWORD)
        self.assertTrue(self.s.recovery.needs_configuration(actor))
        self.s.recovery.configure_questions(actor, USER_PASSWORD, QUESTIONS)
        self.assertFalse(self.s.recovery.needs_configuration(self.row(user_id)))

    def test_23_security_answers_cannot_change_with_wrong_password(self):
        'Verifica la validación y conservación de datos del caso test_23_security_answers_cannot_change_with_wrong_password.'
        self.rejects(AccessDenied, self.s.recovery.configure_questions, self.user, "Incorrecta", QUESTIONS)

    def test_24_recovery_codes_exist_for_all_profiles_and_inactive_account_is_rejected(self):
        'Verifica la validación y conservación de datos del caso test_24_recovery_codes_exist_for_all_profiles_and_inactive_account_is_rejected.'
        for actor in (self.master, self.user, self.admin):
            self.assertFalse(self.s.recovery.needs_code(actor))
        self.s.users.set_user_active(self.master, self.user_id, False)
        self.rejects(AccessDenied, self.s.auth.authenticate_with_code, 'V-10000002', self.user_result.recovery_code)

    def test_25_recovery_rejects_missing_code_and_short_new_password(self):
        'Verifica la validación y conservación de datos del caso test_25_recovery_rejects_missing_code_and_short_new_password.'
        for code in ('', 'Incorrecto'):
            self.rejects(AccessDenied, self.s.auth.authenticate_with_code, 'V-10000001', code)
        actor = self.s.auth.authenticate_with_code('V-10000001', self.master_result.recovery_code)
        self.rejects(ValueError, self.s.auth.change_password, actor, '', '1234567')

    def test_26_wrong_recovery_codes_persist_failure_and_block_after_five_attempts(self):
        'Verifica la validación y conservación de datos del caso test_26_wrong_recovery_codes_persist_failure_and_block_after_five_attempts.'
        with patch('services.auth_service.time.time', return_value=1_000_000):
            for attempt in range(1, 6):
                with self.assertRaises(AccessDenied):
                    self.s.auth.authenticate_with_code('V-10000001', 'Incorrecto')
                key = self.s.auth._attempt_key('V-10000001', 'recovery')
                record = self.s.connection.execute('SELECT * FROM auth_failures WHERE identity_hash=?', (key,)).fetchone()
                self.assertEqual(record['failed_attempts'], attempt)
            self.assertEqual(record['locked_until'], 1_000_900)
            with self.assertRaisesRegex(AccessDenied, 'bloqueado'):
                self.s.auth.authenticate_with_code('V-10000001', self.master_result.recovery_code)

    def test_27_recovery_forces_password_change_and_rotates_code(self):
        'Verifica la validación y conservación de datos del caso test_27_recovery_forces_password_change_and_rotates_code.'
        actor = self.s.auth.authenticate_with_code(' v-10000001 ', ' ' + self.master_result.recovery_code.lower() + ' ')
        self.assertTrue(actor['must_change_password'])
        self.rejects(AccessDenied, self.s.users.users, actor)
        updated = self.s.auth.change_password(actor, '', NEW_PASSWORD)
        self.assertIn('_new_recovery_code', updated)
        self.rejects(AccessDenied, self.s.auth.authenticate_with_code, 'V-10000001', self.master_result.recovery_code)
        self.assertEqual(self.s.auth.authenticate('V-10000001', NEW_PASSWORD, ROLES[0])['id'], self.master_id)

    def test_28_recovery_cannot_reuse_current_password(self):
        'Verifica la validación y conservación de datos del caso test_28_recovery_cannot_reuse_current_password.'
        actor = self.s.auth.authenticate_with_code('V-10000001', self.master_result.recovery_code)
        self.rejects(ValueError, self.s.auth.change_password, actor, '', MASTER_PASSWORD)

    def test_29_recovery_lock_survives_reopening_database_and_expires(self):
        'Verifica la validación y conservación de datos del caso test_29_recovery_lock_survives_reopening_database_and_expires.'
        with tempfile.TemporaryDirectory(prefix='hemeroteca-validaciones-') as directory:
            path = Path(directory) / 'prueba.db'
            temporary = create_services(path)
            self.s.connection.backup(temporary.connection)
            with patch('services.auth_service.time.time', return_value=1_000_000):
                for _ in range(5):
                    with self.assertRaises(AccessDenied):
                        temporary.auth.authenticate_with_code('V-10000001', 'Incorrecto')
            temporary.close()
            reopened = create_services(path)
            try:
                with patch('services.auth_service.time.time', return_value=1_000_001):
                    with self.assertRaisesRegex(AccessDenied, 'bloqueado'):
                        reopened.auth.authenticate_with_code('V-10000001', self.master_result.recovery_code)
                with patch('services.auth_service.time.time', return_value=1_000_901):
                    actor = reopened.auth.authenticate_with_code('V-10000001', self.master_result.recovery_code)
                    self.assertTrue(actor['must_change_password'])
            finally:
                reopened.close()

    def test_30_user_update_rejects_unauthorized_wrong_password_blank_and_duplicate_identity(self):
        'Verifica la validación y conservación de datos del caso test_30_user_update_rejects_unauthorized_wrong_password_blank_and_duplicate_identity.'
        for actor, name, identity, password, error in (
                (self.admin, "Nombre Prueba", "V-20000001", MASTER_PASSWORD, AccessDenied),
                (self.master, "Nombre Prueba", "V-20000001", "Incorrecta", AccessDenied),
                (self.master, " ", "V-20000001", MASTER_PASSWORD, ValueError),
                (self.master, "Nombre Prueba", " ", MASTER_PASSWORD, ValueError),
                (self.master, "Nombre Prueba", "V-10000001", MASTER_PASSWORD, sqlite3.IntegrityError)):
            self.rejects(error, self.s.users.update_user, actor, self.user_id, name, identity, ROLES[2], password)

    def test_31_user_update_changes_data_and_invalidates_previous_session(self):
        'Verifica la validación y conservación de datos del caso test_31_user_update_changes_data_and_invalidates_previous_session.'
        updated = self.s.users.update_user(self.master, self.user_id, "Nombre Nuevo", "V-20000001", ROLES[1], MASTER_PASSWORD, self.user["password_version"])
        self.assertEqual((updated["name"], updated["identity"], updated["role"]), ("Nombre Nuevo", "V-20000001", ROLES[1]))
        self.rejects(AccessDenied, self.s.periodicos.consult_issues, self.user, 2020, 1, 1)

    def test_32_account_operations_reject_outdated_target_version(self):
        'Verifica la validación y conservación de datos del caso test_32_account_operations_reject_outdated_target_version.'
        old = self.user["password_version"]
        self.s.users.update_user(self.master, self.user_id, "Nombre Nuevo", "V-10000002", ROLES[2], MASTER_PASSWORD)
        for function, args in ((self.s.users.reset_password, (self.master, self.user_id, MASTER_PASSWORD, NEW_PASSWORD)),
                               (self.s.users.delete_user, (self.master, self.user_id, MASTER_PASSWORD)),
                               (self.s.users.set_user_active, (self.master, self.user_id, False)),
                               (self.s.users.revoke_grant, (self.master, self.user_id, "Auditoría"))):
            self.rejects(ValueError, function, *args, expected_version=old)

    def test_33_master_cannot_be_deleted_disabled_or_demoted(self):
        'Verifica la validación y conservación de datos del caso test_33_master_cannot_be_deleted_disabled_or_demoted.'
        self.rejects(AccessDenied, self.s.users.delete_user, self.master, self.master_id, MASTER_PASSWORD)
        self.rejects(AccessDenied, self.s.users.set_user_active, self.master, self.master_id, False)
        self.rejects(AccessDenied, self.s.users.update_user, self.master, self.master_id, "Maestro", "V-10000001", ROLES[2], MASTER_PASSWORD)

    def test_34_delete_removes_related_user_data_but_preserves_inventory_and_audit(self):
        'Verifica la validación y conservación de datos del caso test_34_delete_removes_related_user_data_but_preserves_inventory_and_audit.'
        request = self.s.requests.submit_request(self.user, "Registrar ejemplares", "Prueba de permiso")
        self.s.requests.decide_request(self.master, request, True)
        self.s.requests.submit_request(self.user, "Auditoría", "Otra prueba")
        issue_id = self.save_issue()
        self.s.users.delete_user(self.master, self.user_id, MASTER_PASSWORD)
        self.assertIsNone(self.row(self.user_id))
        for table in ("user_security", "grants", "requests"):
            self.assertEqual(self.s.connection.execute(f"SELECT count(*) FROM {table} WHERE user_id=?", (self.user_id,)).fetchone()[0], 0)
        self.assertIsNotNone(self.s.periodicos.get_issue(self.master, issue_id))
        self.assertTrue(any("Cuenta eliminada" in row["action"] for row in self.s.audit.list_events(self.master)))

    def test_35_reused_sqlite_id_does_not_revalidate_deleted_account_session(self):
        'Verifica la validación y conservación de datos del caso test_35_reused_sqlite_id_does_not_revalidate_deleted_account_session.'
        self.s.users.delete_user(self.master, self.admin_id, MASTER_PASSWORD)
        new_id = self.s.users.create_user("Otra persona", "E-20000004", NEW_PASSWORD, security_answers=ANSWERS).user_id
        self.assertEqual(new_id, self.admin_id)
        self.rejects(AccessDenied, self.s.periodicos.consult_issues, self.admin, 2020, 1, 1)

    def test_36_invalid_newspaper_date_title_type_location_and_status_are_rejected(self):
        'Verifica la validación y conservación de datos del caso test_36_invalid_newspaper_date_title_type_location_and_status_are_rejected.'
        invalid = ({"title": "No existe"}, {"kind": "Regional"}, {"shelf": " "}, {"status": "Inventado"},
                   {"year": 1969}, {"year": 2021, "month": 2, "day": 29}, {"month": 0}, {"month": 13}, {"day": 0}, {"day": 32},
                   {"title": REGIONAL[0], "kind": "Regional", "year": 2101}, {"year": 2101})
        for changes in invalid:
            with self.subTest(changes=changes):
                self.rejects(ValueError, self.s.periodicos.save_record, self.master, self.issue_values(**changes))

    def test_37_calendar_accepts_leap_day_1970_and_regional_2021(self):
        'Verifica la validación y conservación de datos del caso test_37_calendar_accepts_leap_day_1970_and_regional_2021.'
        for changes in ({"year": 2020, "month": 2, "day": 29}, {"year": 1970}, {"title": REGIONAL[0], "kind": "Regional", "year": 2021}):
            self.save_issue(**changes)
        self.assertEqual(len(self.s.periodicos.list_issues(self.master)), 3)

    def test_rango_1970_2100_en_alta_edicion_y_ausencias(self):
        """Comprueba todos los títulos y rechaza años inválidos también desde el servicio."""
        for titulo in REGIONAL + NATIONAL:
            tipo = 'Regional' if titulo in REGIONAL else 'Nacional'
            for anio in (1970, 2022, 2100):
                valores = self.issue_values(title=titulo, kind=tipo, year=anio, month=1, day=1)
                self.s.periodicos.save_record(self.master, valores)
                self.s.periodicos.save_record(self.master, (titulo,tipo,anio,1,2,'Prueba de rango'), absent=True)
            identificador = self.s.connection.execute('SELECT id FROM issues WHERE title=? AND year=1970', (titulo,)).fetchone()[0]
            self.s.periodicos.save_record(self.master, self.issue_values(title=titulo,kind=tipo,year=2100,month=12,day=31), issue_id=identificador)
            for anio in (1969, 2101):
                valores = self.issue_values(title=titulo,kind=tipo,year=anio)
                self.rejects(ValueError,self.s.periodicos.save_record,self.master,valores)
                self.rejects(ValueError,self.s.periodicos.save_record,self.master,valores,issue_id=identificador)
                self.rejects(ValueError,self.s.periodicos.save_record,self.master,(titulo,tipo,anio,1,3,'Prueba inválida'),absent=True)

    def test_38_duplicate_issue_is_rejected_and_original_preserved(self):
        'Verifica la validación y conservación de datos del caso test_38_duplicate_issue_is_rejected_and_original_preserved.'
        self.save_issue()
        self.rejects(sqlite3.IntegrityError, self.s.periodicos.save_record, self.master, self.issue_values())

    def test_39_issue_and_absence_cannot_coexist_on_same_day(self):
        'Verifica la validación y conservación de datos del caso test_39_issue_and_absence_cannot_coexist_on_same_day.'
        self.save_issue()
        self.rejects(ValueError, self.s.periodicos.save_record, self.master, self.absent_values(), absent=True)

    def test_40_absence_blocks_issue_and_duplicate_absence(self):
        'Verifica la validación y conservación de datos del caso test_40_absence_blocks_issue_and_duplicate_absence.'
        self.s.periodicos.save_record(self.master, self.absent_values(), absent=True)
        self.rejects(ValueError, self.s.periodicos.save_record, self.master, self.issue_values())
        self.rejects(sqlite3.IntegrityError, self.s.periodicos.save_record, self.master, self.absent_values(), absent=True)

    def test_41_regular_user_cannot_write_edit_delete_or_restore_issues(self):
        'Verifica la validación y conservación de datos del caso test_41_regular_user_cannot_write_edit_delete_or_restore_issues.'
        issue_id = self.save_issue()
        self.rejects(AccessDenied, self.s.periodicos.save_record, self.user, self.issue_values(day=16))
        self.rejects(AccessDenied, self.s.periodicos.delete_issue, self.user, issue_id)
        self.rejects(AccessDenied, self.s.periodicos.restore_issue, self.user, issue_id)
        self.rejects(AccessDenied, self.s.periodicos.restore_issue, self.admin, issue_id)

    def test_42_delete_hides_issue_and_only_master_can_restore_it(self):
        'Verifica la validación y conservación de datos del caso test_42_delete_hides_issue_and_only_master_can_restore_it.'
        issue_id = self.save_issue()
        self.s.periodicos.delete_issue(self.master, issue_id)
        self.assertEqual(self.s.periodicos.consult_issues(self.user, 2020, 4, 15), [])
        self.assertEqual(len(self.s.periodicos.list_deleted_issues(self.master)), 1)
        self.s.periodicos.restore_issue(self.master, issue_id)
        self.assertEqual(len(self.s.periodicos.consult_issues(self.user, 2020, 4, 15)), 1)

    def test_43_restore_rejects_conflicting_absence(self):
        'Verifica la validación y conservación de datos del caso test_43_restore_rejects_conflicting_absence.'
        issue_id = self.save_issue()
        self.s.periodicos.delete_issue(self.master, issue_id)
        self.s.periodicos.save_record(self.master, self.absent_values(), absent=True)
        self.rejects(ValueError, self.s.periodicos.restore_issue, self.master, issue_id)

    def test_44_operations_reject_missing_or_already_deleted_issue(self):
        'Verifica la validación y conservación de datos del caso test_44_operations_reject_missing_or_already_deleted_issue.'
        self.rejects(ValueError, self.s.periodicos.delete_issue, self.master, 99999)
        self.rejects(ValueError, self.s.periodicos.restore_issue, self.master, 99999)
        self.rejects(ValueError, self.s.periodicos.save_record, self.master, self.issue_values(), issue_id=99999)
        self.rejects(ValueError, self.s.periodicos.save_record, self.master, self.absent_values(), absent=True, issue_id=99999)

    def test_45_request_rejects_unknown_permission_and_invalid_reason(self):
        'Verifica la validación y conservación de datos del caso test_45_request_rejects_unknown_permission_and_invalid_reason.'
        self.rejects(ValueError, self.s.requests.submit_request, self.user, "No existe", "Motivo")
        for reason in ("", " ", "x" * 1001):
            self.rejects(ValueError, self.s.requests.submit_request, self.user, "Registrar ejemplares", reason)

    def test_46_request_rejects_existing_permission_or_pending_duplicate(self):
        'Verifica la validación y conservación de datos del caso test_46_request_rejects_existing_permission_or_pending_duplicate.'
        self.s.connection.execute("INSERT INTO grants(user_id,permission) VALUES(?,?)", (self.admin_id, 'Registrar ejemplares'))
        self.s.connection.commit()
        self.rejects(ValueError, self.s.requests.submit_request, self.admin, "Registrar ejemplares", "Motivo")
        self.s.requests.submit_request(self.user, "Registrar ejemplares", "Motivo")
        self.rejects(ValueError, self.s.requests.submit_request, self.user, "Registrar ejemplares", "Motivo repetido")

    def test_47_request_accepts_1000_characters_and_only_master_can_decide(self):
        'Verifica la validación y conservación de datos del caso test_47_request_accepts_1000_characters_and_only_master_can_decide.'
        request = self.s.requests.submit_request(self.user, "Registrar ejemplares", "x" * 1000)
        for actor in (self.user, self.admin, None):
            self.rejects(AccessDenied, self.s.requests.decide_request, actor, request, True)
        self.s.requests.decide_request(self.master, request, True, "Aprobado")
        self.assertIn("Registrar ejemplares", self.s.access.permissions(self.user))
        self.s.periodicos.save_record(self.user, self.issue_values())

    def test_48_rejection_requires_reason_and_response_is_limited(self):
        'Verifica la validación y conservación de datos del caso test_48_rejection_requires_reason_and_response_is_limited.'
        request = self.s.requests.submit_request(self.user, "Auditoría", "Motivo")
        self.rejects(ValueError, self.s.requests.decide_request, self.master, request, False, " ")
        self.rejects(ValueError, self.s.requests.decide_request, self.master, request, True, "x" * 1001)

    def test_49_request_cannot_be_decided_twice_or_for_inactive_user(self):
        'Verifica la validación y conservación de datos del caso test_49_request_cannot_be_decided_twice_or_for_inactive_user.'
        request = self.s.requests.submit_request(self.user, "Auditoría", "Motivo")
        self.s.users.set_user_active(self.master, self.user_id, False)
        self.rejects(ValueError, self.s.requests.decide_request, self.master, request, True)
        self.s.requests.decide_request(self.master, request, False, "Cuenta inactiva")
        self.rejects(ValueError, self.s.requests.decide_request, self.master, request, True)

    def test_50_request_rejects_a_decision_on_changed_account(self):
        'Verifica la validación y conservación de datos del caso test_50_request_rejects_a_decision_on_changed_account.'
        request = self.s.requests.submit_request(self.user, "Auditoría", "Motivo")
        old = self.user["password_version"]
        self.s.users.reset_password(self.master, self.user_id, MASTER_PASSWORD, NEW_PASSWORD)
        self.rejects(ValueError, self.s.requests.decide_request, self.master, request, True, expected_account_version=old)

    def test_51_revocation_takes_effect_during_existing_session(self):
        'Verifica la validación y conservación de datos del caso test_51_revocation_takes_effect_during_existing_session.'
        request = self.s.requests.submit_request(self.user, "Registrar ejemplares", "Motivo")
        self.s.requests.decide_request(self.master, request, True)
        self.s.users.revoke_grant(self.master, self.user_id, "Registrar ejemplares")
        self.rejects(AccessDenied, self.s.periodicos.save_record, self.user, self.issue_values())

    def test_52_regular_user_cannot_view_other_users_requests_or_audit(self):
        'Verifica la validación y conservación de datos del caso test_52_regular_user_cannot_view_other_users_requests_or_audit.'
        self.s.requests.submit_request(self.admin, "Usuarios", "Motivo del administrador")
        self.s.requests.submit_request(self.user, "Auditoría", "Motivo del usuario")
        self.assertEqual(len(self.s.requests.requests(self.user)), 1)
        self.assertEqual(len(self.s.requests.requests(self.master)), 2)
        self.rejects(AccessDenied, self.s.audit.list_events, self.user)
        self.rejects(AccessDenied, self.s.users.users, self.user)

    def test_53_audit_records_denied_access_without_passwords_or_answers(self):
        'Verifica la validación y conservación de datos del caso test_53_audit_records_denied_access_without_passwords_or_answers.'
        with self.assertRaises(AccessDenied):
            self.s.auth.authenticate("V-10000002", "Clave!2026", ROLES[2])
        self.s.auth.change_password(self.user, USER_PASSWORD, NEW_PASSWORD)
        rows = self.s.audit.list_events(self.master)
        self.assertTrue(any(row["result"] == "Acceso denegado" for row in rows))
        text = str([tuple(row) for row in rows])
        for secret in (MASTER_PASSWORD, USER_PASSWORD, ADMIN_PASSWORD, NEW_PASSWORD, "Clave!2026") + ANSWERS:
            self.assertNotIn(secret, text)

    def test_54_filter_dates_validate_calendar_and_accept_empty_filter(self):
        'Verifica la validación y conservación de datos del caso test_54_filter_dates_validate_calendar_and_accept_empty_filter.'
        for value in ("", " "):
            self.assertIsNone(parse_filter_date(value))
        for value in ("29/02/2020", "2020-02-29"):
            self.assertEqual(parse_filter_date(value), date(2020, 2, 29))
        for value in ("29/02/2021", "31/04/2020", "00/01/2020", "01/13/2020", "abc", "15/10"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_filter_date(value)


class FormValidationTests(unittest.TestCase):
    """Comprueba los manejadores con campos simulados, sin automatizar el escritorio."""

    def registration_form(self, name=" Persona Prueba ", identity="V-20000001", password=USER_PASSWORD, confirmation=USER_PASSWORD, setup=False):
        """Simula los campos y callbacks del registro para comprobar validaciones sin abrir una ventana."""
        field = lambda value: Mock(get=Mock(return_value=value))
        return SimpleNamespace(
            reg_name=(None, field(name)), login_identity=field(identity),
            login_password=field(password), reg_confirm=field(confirmation),
            _setup_mode=setup, _security_questions_form=Mock(),
        )

    @patch("ui.login_view.messagebox.showwarning")
    def test_55_form_blocks_missing_fields_and_short_password(self, warning):
        'Verifica la validación y conservación de datos del caso test_55_form_blocks_missing_fields_and_short_password.'
        for fields in ({"name": " "}, {"identity": " "}, {"password": "1234567", "confirmation": "1234567"}):
            warning.reset_mock()
            form = self.registration_form(**fields)
            LoginView.register_user(form)
            warning.assert_called_once()
            form._security_questions_form.assert_not_called()

    @patch("ui.login_view.messagebox.showwarning")
    def test_56_form_blocks_password_confirmation_mismatch(self, warning):
        'Verifica la validación y conservación de datos del caso test_56_form_blocks_password_confirmation_mismatch.'
        form = self.registration_form(confirmation=NEW_PASSWORD)
        LoginView.register_user(form)
        self.assertIn("no coinciden", warning.call_args.args[1])
        form._security_questions_form.assert_not_called()

    @patch("ui.login_view.messagebox.showwarning")
    def test_57_initial_form_routes_to_master_security_questions(self, warning):
        'Verifica la validación y conservación de datos del caso test_57_initial_form_routes_to_master_security_questions.'
        form = self.registration_form(setup=True)
        LoginView.register_user(form)
        warning.assert_not_called()
        form._security_questions_form.assert_called_once_with(account_data=("Persona Prueba", "V-20000001", USER_PASSWORD, ROLES[0]))

    @patch("ui.login_view.messagebox.showwarning")
    def test_58_public_form_can_only_route_to_regular_user_registration(self, warning):
        'Verifica la validación y conservación de datos del caso test_58_public_form_can_only_route_to_regular_user_registration.'
        form = self.registration_form()
        form.reg_role = Mock(get=Mock(return_value=ROLES[2]))
        LoginView.register_user(form)
        warning.assert_not_called()
        form._security_questions_form.assert_called_once_with(account_data=("Persona Prueba", "V-20000001", USER_PASSWORD, ROLES[2]))

    @patch("ui.login_view.messagebox.showerror")
    def test_59_failed_login_clears_password_and_does_not_open_session(self, error):
        'Verifica la validación y conservación de datos del caso test_59_failed_login_clears_password_and_does_not_open_session.'
        form = self.registration_form()
        form.login_role = Mock(get=Mock(return_value=ROLES[2]))
        form.services = SimpleNamespace(auth=Mock(authenticate=Mock(side_effect=AccessDenied("Credenciales incorrectas"))))
        form.show_shell = Mock()
        LoginView.login(form)
        error.assert_called_once()
        form.login_password.delete.assert_called_once_with(0, "end")
        form.login_password.focus_set.assert_called_once()
        form.show_shell.assert_not_called()

    @patch("ui.login_view.messagebox.showerror")
    def test_60_successful_login_stores_session_version_and_opens_consultation(self, error):
        'Verifica la validación y conservación de datos del caso test_60_successful_login_stores_session_version_and_opens_consultation.'
        form = self.registration_form()
        form.login_role = Mock(get=Mock(return_value=ROLES[2]))
        actor = {"id": 10, "password_version": 123}
        form.services = SimpleNamespace(auth=Mock(authenticate=Mock(return_value=actor)))
        form.show_shell = Mock()
        LoginView.login(form)
        error.assert_not_called()
        self.assertEqual(form.user, actor)
        self.assertEqual(form._authenticated_version, 123)
        form.show_shell.assert_called_once_with("Consulta de periódicos")


if __name__ == "__main__":
    unittest.main(verbosity=2)
