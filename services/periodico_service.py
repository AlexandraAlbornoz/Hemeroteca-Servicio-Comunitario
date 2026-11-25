"""Consulta, registro, edición, retiro y restauración de ejemplares."""

from services.base import ServicioConAcceso
from services.paginacion import paginar, validar_paginacion

from utils.validaciones import validar_numero, validar_edicion
from datetime import date

from config.settings import ISSUE_STATUSES, RECORD_PERIODS, REGIONAL, TITLES, VIEWS, ROLES
from services.access_service import AccessDenied
from utils.timestamps import utc_now
from services.audit_service import append_event


def agregar_rango(condiciones, parametros, expresion, desde, hasta):
    """Valida fechas ISO desde 1970 y añade un intervalo inclusivo parametrizado."""
    limites = []
    for valor in (desde, hasta):
        fecha = date.fromisoformat(valor) if valor else None
        if fecha and fecha.year < 1970:
            raise ValueError('Selecciona fechas desde 1970.')
        limites.append(fecha)
    if all(limites) and limites[0] > limites[1]:
        raise ValueError('La fecha Desde no puede ser posterior a Hasta.')
    for operador, valor in zip(('>=', '<='), (desde, hasta)):
        if valor:
            condiciones.append(expresion + operador + '?')
            parametros.append(valor)


def consulta_busqueda_ejemplares(*, title=None, kind=None, year=None, month=None, day=None, period=None, desde=None, hasta=None):
    """Mismos filtros y orden para pantalla y PDF, sin depender de la paginación."""
    periodo = period
    dia = day
    tipo = kind
    mes = month
    titulo = title
    anio = year
    if periodo is not None and periodo not in RECORD_PERIODS:
        raise ValueError("Selecciona un periodo válido.")
    condiciones, parametros = ["deleted=0"], []
    agregar_rango(condiciones, parametros, "printf('%04d-%02d-%02d',year,month,day)", desde, hasta)
    for columna, valor in (("title", titulo), ("kind", tipo), ("year", anio), ("month", mes), ("day", dia)):
        if valor is not None:
            if columna in ("year", "month", "day") and type(valor) is not int:
                raise ValueError("Los filtros de fecha deben ser números enteros.")
            if columna in ("title", "kind") and not isinstance(valor, str):
                raise ValueError("El periódico y el tipo de prensa deben ser texto.")
            condiciones.append(columna + "=?")
            parametros.append(valor)
    if anio is not None and not 1970 <= anio <= 9999:
        raise ValueError("El año debe estar entre 1970 y 9999.")
    if (mes is not None and not 1 <= mes <= 12) or (dia is not None and not 1 <= dia <= 31):
        raise ValueError("Selecciona un mes y día válidos.")
    if anio is not None and mes is not None and dia is not None:
        date(anio, mes, dia)
    intervalos = {"Último día (24h)": "-1 day", "Última semana": "-7 days", "Últimos 15 días": "-15 days", "Último mes": "-30 days"}
    if periodo in intervalos:
        ahora = utc_now()
        condiciones.append("datetime(created_at) BETWEEN datetime(?, ?) AND datetime(?)")
        parametros.extend((ahora, intervalos[periodo], ahora))
    consulta = "SELECT * FROM issues WHERE " + " AND ".join(condiciones) + " ORDER BY id DESC"
    if periodo == "Últimos 5 registros":
        consulta += " LIMIT 5"
    return consulta, parametros
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
issue_search_query = consulta_busqueda_ejemplares


class ServicioPeriodicos(ServicioConAcceso):
    """Valida y gestiona ejemplares y fechas sin publicación, con filtros, paginación y auditoría de cambios."""
    def buscar_eliminados(self, actor, *, texto='', pagina=1, desde=None, hasta=None, periodo=None):
        """Busca ejemplares retirados en SQL usando el mismo texto visible de antes."""
        responsable = actor
        from services.paginacion import paginar
        self.access.require_access(responsable, VIEWS[5], action='Consultar eliminados paginados', view=True)
        if not isinstance(texto, str):
            raise ValueError('Escribe un texto de búsqueda válido.')
        consulta = "SELECT issues.*,(SELECT instante_evento(at) FROM audit WHERE action='Ejemplar eliminado: #' || issues.id ORDER BY id DESC LIMIT 1) AS eliminado_el FROM issues WHERE deleted=1 AND instr(plegar_texto(title || ' ' || coalesce(edition,'None') || ' ' || printf('%02d/%02d/%d',day,month,year)),?)>0"
        condiciones, parametros = [], [texto.strip().casefold()]
        agregar_rango(condiciones, parametros, "substr((SELECT instante_evento(at) FROM audit WHERE action='Ejemplar eliminado: #' || issues.id ORDER BY id DESC LIMIT 1),1,10)", desde, hasta)
        if periodo:
            intervalos = {'24h': '-1 day', '1 semana': '-7 days', '1 mes': '-30 days'}
            if periodo not in intervalos:
                raise ValueError('Periodo de eliminación no válido.')
            condiciones.append("datetime((SELECT instante_evento_utc(at) FROM audit WHERE action='Ejemplar eliminado: #' || issues.id ORDER BY id DESC LIMIT 1)) BETWEEN datetime(?,?) AND datetime(?)")
            ahora = utc_now()
            parametros.extend((ahora, intervalos[periodo], ahora))
        if condiciones:
            consulta += ' AND ' + ' AND '.join(condiciones)
        return paginar(self.conn, consulta, parametros, pagina=pagina)


    def buscar_fechas_ausentes(self, actor, *, title=None, kind=None, year=None, month=None, day=None, page=1, page_size=5, observaciones='Todas', desde=None, hasta=None):
        """Filtra anotaciones en SQL y devuelve únicamente la página solicitada."""
        pagina_size_local = page_size
        pagina_size = pagina_size_local
        responsable = actor
        dia = day
        tipo = kind
        mes = month
        pagina_local = page
        tamano_pagina = pagina_size
        titulo = title
        anio = year
        self.access.require_access(responsable, VIEWS[1], action='Consultar fechas sin publicación', view=True)
        validar_paginacion(pagina_local, tamano_pagina, 'La página o su tamaño no son válidos.')
        consulta, parametros = issue_search_query(title=titulo, kind=tipo, year=anio, month=mes, day=dia, desde=desde, hasta=hasta)
        consulta = consulta.replace('FROM issues WHERE deleted=0', 'FROM absent_dates WHERE 1=1')
        if observaciones not in ('Todas', 'Con observación', 'Sin observación'):
            raise ValueError('Selecciona un filtro de observaciones válido.')
        if observaciones != 'Todas':
            condicion = "trim(coalesce(note,''))" + ("<>''" if observaciones == 'Con observación' else "=''")
            consulta = consulta.replace(' ORDER BY ', ' AND ' + condicion + ' ORDER BY ')
        consulta_conteo = consulta.rsplit(' ORDER BY ', 1)[0]
        return paginar(self.conn, consulta, parametros, pagina=pagina_local, tamano=tamano_pagina, consulta_conteo=consulta_conteo)

    def corregir_fecha_ausente(self, actor, identificador, *, anular=False, observacion=None):
        """Corrige una nota o anula una anotación equivocada conservando su auditoría."""
        responsable = actor
        if type(identificador) is not int or identificador < 1 or type(anular) is not bool:
            raise ValueError('Selecciona una fecha sin publicación válida.')
        if not anular and (not isinstance(observacion, str) or len(observacion) > 1000):
            raise ValueError('Escribe una observación de hasta 1.000 caracteres.')
        with self.access.authorized_write(responsable, 'Registrar ejemplares', action='Corregir fecha sin publicación') as usuario:
            fila = self.conn.execute('SELECT * FROM absent_dates WHERE id=?', (identificador,)).fetchone()
            if fila is None:
                raise ValueError('La anotación ya cambió o fue retirada. Actualiza la lista.')
            if anular:
                self.conn.execute('DELETE FROM absent_dates WHERE id=?', (identificador,))
            else:
                self.conn.execute('UPDATE absent_dates SET note=? WHERE id=?', (observacion.strip(), identificador))
            detalle = f"{fila['title']} {fila['day']}/{fila['month']}/{fila['year']} · Nota anterior: {fila['note'] or 'Sin observación'}"
            append_event(self.conn, self.access.actor_label(usuario), ('Anulación' if anular else 'Corrección') + ' de fecha sin publicación: ' + detalle)

    def registrar_ejemplar(self, actor, values):
        """Alta desde una PC autorizada: administrador regular con acceso al catálogo."""
        responsable = actor
        valores = values
        actual = self.access.require_access(responsable, VIEWS[1], action='Registrar ejemplar desde una PC secundaria')
        if actual['role'] != ROLES[1]:
            raise AccessDenied('El registro desde una PC secundaria requiere un administrador regular con permiso de Catálogo.')
        if not isinstance(valores, (list, tuple)) or len(valores) != 10:
            raise ValueError('Completa todos los campos del ejemplar.')
        if any(type(valores[indice]) is not int for indice in (3, 4, 5)):
            raise ValueError('Selecciona un año, mes y día válidos.')
        self.save_record(actual, tuple(valores), _catalog_registration=True)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    register_issue = registrar_ejemplar

    def guardar_registro(self, actor, values, *, absent=False, issue_id=None, _catalog_registration=False, expected_revision=None):
        'Valida y guarda un ejemplar o fecha sin publicación con autorización transaccional.'
        _catalogo_registration = _catalog_registration
        ejemplar_id_local = issue_id
        _catalogo_registration_local = _catalogo_registration
        revision_esperada = expected_revision
        ejemplar_id = ejemplar_id_local
        _registro_por_catalogo = _catalogo_registration_local
        sin_publicacion = absent
        responsable = actor
        identificador_ejemplar = ejemplar_id
        valores = values
        permiso = "Registrar ejemplares" if sin_publicacion else "Editar ejemplares" if identificador_ejemplar is not None else "Registrar ejemplares"
        if _registro_por_catalogo:
            if sin_publicacion or identificador_ejemplar is not None:
                raise ValueError('El acceso por Catálogo permite registrar únicamente ejemplares nuevos.')
            permiso = VIEWS[1]
        elif not sin_publicacion and identificador_ejemplar is None:
            actual = self.access.current_user(responsable)
            if actual and actual['role'] == ROLES[1] and VIEWS[1] in self.access.permissions(actual):
                permiso = VIEWS[1]
        accion = "Editar ejemplar" if identificador_ejemplar is not None else "Registrar fecha sin publicación" if sin_publicacion else "Registrar ejemplar"
        with self.access.authorized_write(responsable, permiso, action=accion) as responsable:
            if permiso == VIEWS[1] and responsable['role'] != ROLES[1]:
                raise AccessDenied('Registrar con permiso de Catálogo requiere el perfil de administrador regular.')
            if type(sin_publicacion) is not bool:
                raise ValueError("El tipo de registro no es válido.")
            if identificador_ejemplar is not None and (type(identificador_ejemplar) is not int or identificador_ejemplar < 1):
                raise ValueError("Selecciona un ejemplar válido.")
            if revision_esperada is not None and (type(revision_esperada) is not int or revision_esperada < 0):
                raise ValueError('La revisión del ejemplar no es válida.')
            if sin_publicacion and identificador_ejemplar is not None:
                raise ValueError("Una fecha sin publicación se registra por separado del ejemplar.")
            if not isinstance(valores, (list, tuple)) or len(valores) != (6 if sin_publicacion else 10):
                raise ValueError("Completa todos los campos del registro.")
            # JSON transporta listas; el servicio usa la misma tupla en local y LAN.
            valores = tuple(valores)
            fecha_indexes = (2, 3, 4) if sin_publicacion else (3, 4, 5)
            if any(type(valores[indice]) is not int for indice in fecha_indexes):
                raise ValueError("Selecciona un año, mes y día válidos.")
            if sin_publicacion:
                titulo, tipo, anio_breve, mes_breve, dia_breve, nota = valores
                if not all(isinstance(valor, str) for valor in (titulo, tipo, nota)) or len(nota) > 1000:
                    raise ValueError("Revisa el periódico, tipo de prensa y observación.")
            else:
                titulo, tipo, edicion, anio_breve, mes_breve, dia_breve, numero, estante, gaveta, estado = valores
                for etiqueta, valor in (("Periódico", titulo), ("Tipo de prensa", tipo), ("Edición", edicion), ("Número", numero), ("Estante", estante), ("Gaveta", gaveta), ("Estado", estado)):
                    if not isinstance(valor, str) or (etiqueta not in ("Estante", "Gaveta") and not valor.strip()):
                        raise ValueError(f"El campo {etiqueta} es obligatorio.")
                validar_edicion(edicion)
                validar_numero(numero, 'Número de edición')
                validar_numero(estante, 'Estante', opcional=True)
                validar_numero(gaveta, 'Gaveta', opcional=True)
                if not estante and not gaveta:
                    raise ValueError('Indica al menos un estante o una gaveta.')
                if estado not in ISSUE_STATUSES:
                    raise ValueError("Selecciona un estado válido para el ejemplar.")
            if titulo not in TITLES or tipo != ("Regional" if titulo in REGIONAL else "Nacional"):
                raise ValueError("Selecciona un periódico y tipo de prensa válidos.")
            date(anio_breve, mes_breve, dia_breve)
            from utils.dates import validar_anio_publicacion
            validar_anio_publicacion(anio_breve)
            opposite = "issues" if sin_publicacion else "absent_dates"
            extra = " AND deleted=0" if sin_publicacion else ""
            if self.conn.execute(f"SELECT 1 FROM {opposite} WHERE title=? AND year=? AND month=? AND day=?{extra}", (titulo, anio_breve, mes_breve, dia_breve)).fetchone():
                raise ValueError("La fecha ya figura con ejemplares o sin publicación. Revisa el registro existente.")
            creado = (responsable["name"], utc_now())
            if sin_publicacion:
                self.conn.execute("INSERT INTO absent_dates(title,kind,year,month,day,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)", valores + creado)
            elif identificador_ejemplar is not None:
                condicion = ' AND revision=?' if revision_esperada is not None else ''
                parametros = valores + (identificador_ejemplar,) + ((revision_esperada,) if revision_esperada is not None else ())
                modificado = self.conn.execute("UPDATE issues SET title=?,kind=?,edition=?,year=?,month=?,day=?,number=?,shelf=?,drawer=?,status=?,revision=revision+1 WHERE id=? AND deleted=0" + condicion, parametros)
                if not modificado.rowcount:
                    raise ValueError("El ejemplar cambió o ya no está disponible. Conserva tus datos y abre la ficha actual antes de volver a guardar.")
            else:
                self.conn.execute("INSERT INTO issues(title,kind,edition,year,month,day,number,shelf,drawer,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", valores + creado)
            append_event(self.conn, self.access.actor_label(responsable), f"{accion}: {titulo} {dia_breve}/{mes_breve}/{anio_breve}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    save_record = guardar_registro

    def eliminar_ejemplar(self, actor, issue_id):
        'Retira lógicamente el ejemplar y registra la operación en auditoría.'
        ejemplar_id_local = issue_id
        ejemplar_id = ejemplar_id_local
        responsable = actor
        identificador_ejemplar = ejemplar_id
        with self.access.authorized_write(responsable, "Eliminar ejemplares", action=f"Eliminar ejemplar #{identificador_ejemplar}") as responsable:
            if type(identificador_ejemplar) is not int or identificador_ejemplar < 1:
                raise ValueError("Selecciona un ejemplar válido.")
            modificado = self.conn.execute("UPDATE issues SET deleted=1,revision=revision+1 WHERE id=? AND deleted=0", (identificador_ejemplar,))
            if not modificado.rowcount:
                raise ValueError("El ejemplar ya no está disponible. Actualiza el catálogo.")
            append_event(self.conn, self.access.actor_label(responsable), f"Ejemplar eliminado: #{identificador_ejemplar}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    delete_issue = eliminar_ejemplar

    def restaurar_ejemplar(self, actor, issue_id):
        'Reincorpora un ejemplar retirado si no existe conflicto de publicación.'
        ejemplar_id_local = issue_id
        ejemplar_id = ejemplar_id_local
        responsable = actor
        identificador_ejemplar = ejemplar_id
        with self.access.authorized_write(responsable, action=f"Restaurar ejemplar #{identificador_ejemplar}", master=True) as responsable:
            registro = self.conn.execute("SELECT * FROM issues WHERE id=? AND deleted=1", (identificador_ejemplar,)).fetchone()
            if registro is None:
                raise ValueError("El ejemplar ya no está disponible para restaurar.")
            if self.conn.execute("SELECT 1 FROM absent_dates WHERE title=? AND year=? AND month=? AND day=?", (registro["title"], registro["year"], registro["month"], registro["day"])).fetchone():
                raise ValueError("Esta fecha está registrada sin publicación. Revisa esa anotación antes de restaurar.")
            self.conn.execute("UPDATE issues SET deleted=0,revision=revision+1 WHERE id=?", (identificador_ejemplar,))
            append_event(self.conn, self.access.actor_label(responsable), f"Ejemplar restaurado: #{identificador_ejemplar} · {registro['title']}")
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    restore_issue = restaurar_ejemplar

    def consultar_issues(self, actor, year, month, day):
        """Consulta ejemplares activos de una fecha después de comprobar el permiso de Consulta de periódicos."""
        responsable = actor
        dia = day
        mes = month
        anio = year
        self.access.require_access(responsable, VIEWS[0], action="Consultar periódicos", view=True)
        date(anio, mes, dia)
        return self.conn.execute(
            "SELECT * FROM issues WHERE deleted=0 AND year=? AND month=? AND day=? ORDER BY id DESC",
            (anio, mes, dia),
        ).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    consult_issues = consultar_issues

    def consultar_absent_dates(self, actor, year, month, day):
        """Consulta anotaciones sin publicación de una fecha bajo el permiso de Consulta de periódicos."""
        responsable = actor
        dia = day
        mes = month
        anio = year
        self.access.require_access(responsable, VIEWS[0], action="Consultar fechas sin publicación", view=True)
        date(anio, mes, dia)
        return self.conn.execute(
            "SELECT * FROM absent_dates WHERE year=? AND month=? AND day=? ORDER BY id DESC", (anio, mes, dia)
        ).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    consult_absent_dates = consultar_absent_dates

    def listar_issues(self, actor):
        """Devuelve los ejemplares activos completos para los llamadores autorizados del contrato anterior."""
        responsable = actor
        self.access.require_access(responsable, VIEWS[1], action="Consultar catálogo", view=True)
        return self.conn.execute(
            "SELECT * FROM issues WHERE deleted=0 ORDER BY id DESC"
        ).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    list_issues = listar_issues

    def listar_absent_dates(self, actor):
        """Devuelve todas las anotaciones sin publicación después de autorizar el acceso al catálogo."""
        responsable = actor
        self.access.require_access(responsable, VIEWS[1], action="Consultar fechas sin publicación", view=True)
        return self.conn.execute(
            "SELECT * FROM absent_dates ORDER BY id DESC"
        ).fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    list_absent_dates = listar_absent_dates

    def obtener_ejemplar(self, actor, issue_id, *, permission="Catálogo de periódicos"):
        'Comprueba el permiso solicitado y recupera un ejemplar activo por su identificador.'
        ejemplar_id_local = issue_id
        ejemplar_id = ejemplar_id_local
        responsable = actor
        identificador_ejemplar = ejemplar_id
        permiso = permission
        if permiso not in {VIEWS[1], "Editar ejemplares", "Eliminar ejemplares"}:
            raise ValueError("Permiso de consulta de ejemplares no válido.")
        self.access.require_access(responsable, permiso, action=f"Consultar ejemplar #{identificador_ejemplar}", view=permiso == VIEWS[1])
        return self.conn.execute("SELECT * FROM issues WHERE id=? AND deleted=0", (identificador_ejemplar,)).fetchone()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    get_issue = obtener_ejemplar

    def listar_eliminados_issues(self, actor):
        """Devuelve los ejemplares retirados después de verificar el acceso a Registros eliminados."""
        responsable = actor
        self.access.require_access(responsable, VIEWS[5], action="Consultar registros eliminados", view=True)
        return self.conn.execute("SELECT * FROM issues WHERE deleted=1 ORDER BY id DESC").fetchall()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    list_deleted_issues = listar_eliminados_issues

    def obtener_eliminados_ejemplar(self, actor, issue_id):
        """Obtiene un ejemplar retirado por identificador con acceso autorizado a Registros eliminados."""
        ejemplar_id_local = issue_id
        ejemplar_id = ejemplar_id_local
        responsable = actor
        identificador_ejemplar = ejemplar_id
        self.access.require_access(responsable, VIEWS[5], action="Consultar ejemplar eliminado", view=True)
        return self.conn.execute("SELECT * FROM issues WHERE id=? AND deleted=1", (identificador_ejemplar,)).fetchone()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    get_deleted_issue = obtener_eliminados_ejemplar

    def tiene_absent_fecha(self, actor, title, year, month, day):
        """Comprueba si existe una anotación sin publicación para el periódico y la fecha indicados."""
        responsable = actor
        dia = day
        mes = month
        titulo = title
        anio = year
        self.access.require_access(responsable, action="Revisar fecha antes de restaurar", master=True)
        return self.conn.execute(
            "SELECT 1 FROM absent_dates WHERE title=? AND year=? AND month=? AND day=?",
            (titulo, anio, mes, dia),
        ).fetchone() is not None
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    has_absent_date = tiene_absent_fecha

    def search_issues(self, actor, *, catalog=False, title=None, kind=None, year=None, month=None, day=None, period=None, page=1, page_size=8, desde=None, hasta=None):
        'Valida filtros y permisos, cuenta coincidencias y devuelve una página de ejemplares.'
        pagina_size_local = page_size
        pagina_size = pagina_size_local
        periodo = period
        responsable = actor
        dia = day
        tipo = kind
        mes = month
        pagina = page
        tamano_pagina = pagina_size
        titulo = title
        anio = year
        if type(catalog) is not bool:
            raise ValueError('El ámbito de consulta no es válido.')
        self.access.require_access(responsable, VIEWS[1] if catalog else VIEWS[0], action="Consultar registros paginados", view=True)
        validar_paginacion(pagina, tamano_pagina)
        consulta, parametros = issue_search_query(title=titulo, kind=tipo, year=anio, month=mes, day=dia, period=periodo, desde=desde, hasta=hasta)
        consulta_conteo = consulta if periodo == 'Últimos 5 registros' else consulta.rsplit(' ORDER BY ', 1)[0]
        return paginar(self.conn, consulta, parametros, pagina=pagina, tamano=tamano_pagina, consulta_conteo=consulta_conteo)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
PeriodicoService = ServicioPeriodicos
