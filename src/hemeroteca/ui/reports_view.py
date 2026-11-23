"""Exportación de PDF con filtros y comprobación de permisos antes de guardarlo."""

import base64
import queue
import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from hemeroteca.config.settings import (BG, FONT, INK, MONTHS, RECORD_PERIODS, TITLES, VIEWS, WHITE,
                             REPORT_ISSUES_PERMISSION, REPORT_DATABASE_PERMISSION)
from hemeroteca.utils.local_secrets import private_write


class VistaReportes:
    """Permite configurar y exportar informes PDF según las secciones y permisos disponibles para la cuenta."""
    def _reportes_pagina(self):
        'Construye los controles de reportes pagina y conecta las acciones con los servicios autorizados.'
        if not self._require_access(VIEWS[6], action='Abrir reportes PDF', view=True):
            return
        self._heading('Documentos', 'Reportes PDF', 'Guarda un documento en esta computadora o en una memoria USB, según los permisos de tu cuenta.')
        fila = 1
        if self._can(REPORT_ISSUES_PERMISSION):
            tarjeta = self._card(fila)
            fila += 1
            self._label(tarjeta, 'Ejemplares activos: todos o filtrados').pack(anchor='w', padx=20, pady=(18, 8))
            self._paragraph(tarjeta, 'El PDF incluye todos los registros que coincidan con los filtros, en todas sus páginas. Si dejas Todos, se exporta la colección activa completa.').pack(fill='x', padx=20, pady=(0, 14))
            panel = ctk.CTkFrame(tarjeta, fg_color='transparent')
            panel.pack(fill='x', padx=16)
            panel.grid_columnconfigure((0, 1, 2), weight=1, uniform='report_filters')
            envoltura_titulo, titulo = self._combo(panel, 'Periódico', ['Todos los periódicos'] + TITLES, 'Todos los periódicos')
            envoltura_titulo.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=(0, 12))
            opciones_extra, tipo = self._combo(panel, 'Tipo de prensa', ['Todos', 'Regional', 'Nacional'], 'Todos')
            opciones_extra.grid(row=0, column=2, sticky='ew', padx=5, pady=(0, 12))
            envoltura_anio, anio = self._combo(panel, 'Año de publicación', ['Todos'] + [str(anio_breve) for anio_breve in range(date.today().year, 1969, -1)], 'Todos')
            envoltura_mes, mes = self._combo(panel, 'Mes de publicación', ['Todos'] + MONTHS, 'Todos')
            envoltura_dia, dia = self._combo(panel, 'Día de publicación', ['Todos'] + [str(dia_breve) for dia_breve in range(1, 32)], 'Todos')
            for columna, control in enumerate((envoltura_anio, envoltura_mes, envoltura_dia)):
                control.grid(row=1, column=columna, sticky='ew', padx=5, pady=(0, 12))
            self._connect_date_fields(anio, mes, dia, allow_all=True)
            envoltura_periodo, periodo = self._combo(panel, 'Periodo desde el registro en el sistema', ['Todos los registros'] + list(RECORD_PERIODS), 'Todos los registros')
            envoltura_periodo.grid(row=2, column=0, columnspan=3, sticky='ew', padx=5, pady=(0, 12))
            def exportar_issues():
                """Convierte los selectores a filtros del servicio y solicita un PDF de los ejemplares coincidentes."""
                filtros = {'title': None if titulo.get() == 'Todos los periódicos' else titulo.get(),
                           'kind': None if tipo.get() == 'Todos' else tipo.get(),
                           'year': None if anio.get() == 'Todos' else int(anio.get()),
                           'month': None if mes.get() == 'Todos' else MONTHS.index(mes.get()) + 1,
                           'day': None if dia.get() == 'Todos' else int(dia.get()),
                           'period': None if periodo.get() == 'Todos los registros' else periodo.get()}
                self._export_pdf(scope='issues', filters=filtros)
            # Alias del contrato anterior: conserva integraciones y llamadas RPC.
            exportar_issues_local = exportar_issues
            self._primary(tarjeta, 'Guardar PDF de ejemplares', exportar_issues_local, width=240).pack(anchor='e', padx=20, pady=(4, 20))
        if self._can(REPORT_DATABASE_PERMISSION):
            tarjeta = self._card(fila)
            self._label(tarjeta, 'Contenido general del sistema').pack(anchor='w', padx=20, pady=(18, 8))
            self._paragraph(tarjeta, 'Incluye ejemplares activos y eliminados, fechas sin publicación, cuentas, permisos, solicitudes, auditoría y computadoras autorizadas. Puede contener datos personales.').pack(fill='x', padx=20, pady=(0, 10))
            self._paragraph(tarjeta, 'Las contraseñas, respuestas de seguridad, códigos de recuperación, sesiones y claves técnicas no se muestran. Para restaurar la base utiliza Respaldos de seguridad.').pack(fill='x', padx=20, pady=(0, 12))
            self._primary(tarjeta, 'Guardar PDF general', lambda: self._export_pdf(scope='database'), width=215).pack(anchor='e', padx=20, pady=(4, 20))
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _reports_page = _reportes_pagina

    def _exportar_pdf(self, *, scope='issues', filters=None):
        'Genera el PDF en segundo plano y verifica la sesión antes de guardarlo.'
        filtros = filters
        ambito = scope
        permiso = REPORT_ISSUES_PERMISSION if ambito == 'issues' else REPORT_DATABASE_PERMISSION
        if not self._require_access(permiso, action='Exportar PDF'):
            return
        destino = filedialog.asksaveasfilename(parent=self, title='Guardar reporte PDF',
            defaultextension='.pdf', filetypes=[('Documento PDF', '*.pdf')],
            initialfile=f"hemeroteca-{'ejemplares' if ambito == 'issues' else 'general'}-{datetime.now():%Y%m%d-%H%M%S}.pdf")
        if not destino:
            return
        responsable = dict(self.user)
        servicios_originales = self.services
        resultados = queue.Queue()
        progreso = self._dialog('Generando reporte PDF', '540x280')
        self._label(progreso, 'Preparando el documento...').pack(anchor='w', padx=24, pady=(28, 12))
        self._paragraph(progreso, 'Se incluyen todas las páginas del resultado. Puedes cancelar la descarga; los datos guardados no cambian.').pack(fill='x', padx=24, pady=(0, 16))
        self._button(progreso, 'Cancelar descarga', progreso.destroy, 'secondary', width=180).pack(anchor='e', padx=24, pady=12)
        if servicios_originales.read_only:
            remote_configuracion = dict(servicios_originales.client.settings)
            remote_token = servicios_originales.client.token
        else:
            base_datos = servicios_originales.backups.database
            nodo = servicios_originales.access.node_id
        def generar():
            'Genera un reporte autorizado y vuelve a comprobar permisos antes de entregarlo.'
            temporal = None
            try:
                if servicios_originales.read_only:
                    from hemeroteca.network.client import RemoteClient, RemoteServices
                    cliente = RemoteClient(remote_configuracion)
                    cliente.token = remote_token
                    servicio = RemoteServices(cliente, None).reports
                else:
                    from hemeroteca.services.container import create_services
                    temporal = create_services(base_datos, node_id=nodo, initialize=False)
                    servicio = temporal.reports
                resultados.put((True, servicio.generate(responsable, scope=ambito, filters=filtros)))
            except Exception as excepcion:
                resultados.put((False, str(excepcion) if isinstance(excepcion, (ValueError, OSError)) else 'No se pudo generar el PDF. Revisa las dependencias y el servidor.'))
            finally:
                if temporal:
                    temporal.close()
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        generate = generar
        def recibir():
            'Recoge el resultado pendiente y actualiza la interfaz desde su hilo.'
            if not progreso.winfo_exists():
                return
            try:
                success, valor = resultados.get_nowait()
            except queue.Empty:
                self.after(150, receive)
                return
            progreso.destroy()
            if not success:
                messagebox.showerror('No se guardó el PDF', valor, parent=self)
                return
            if self.services is not servicios_originales or self.user is None or self.user['id'] != responsable['id'] or self.user['password_version'] != responsable['password_version']:
                messagebox.showwarning('Descarga cancelada', 'La sesión cambió. Inicia de nuevo la exportación.', parent=self)
                return
            if not self._require_access(permiso, action='Guardar PDF descargado'):
                return
            try:
                if (not isinstance(valor, dict) or not isinstance(valor.get('content'), str)
                        or type(valor.get('records')) is not int or valor['records'] < 0):
                    raise ValueError('La respuesta no es un PDF compatible.')
                contenido = base64.b64decode(valor['content'], validate=True)
                if not contenido.startswith(b'%PDF-') or len(contenido) > 64 * 1024 * 1024 or Path(destino).suffix.lower() != '.pdf':
                    raise ValueError('La respuesta no es un PDF compatible.')
                private_write(destino, contenido)
            except (OSError, ValueError) as excepcion:
                messagebox.showerror('No se pudo guardar', str(excepcion), parent=self)
                return
            messagebox.showinfo('PDF guardado', f"Se guardó el reporte con {valor['records']} registros en:\n{destino}", parent=self)
            self._notice('Reporte PDF guardado. Puedes copiarlo a una memoria USB.')
        # Alias del contrato anterior: conserva integraciones y llamadas RPC.
        receive = recibir
        threading.Thread(target=generate, daemon=True, name='hemeroteca-pdf').start()
        self.after(150, receive)
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    _export_pdf = _exportar_pdf
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
ReportsView = VistaReportes
