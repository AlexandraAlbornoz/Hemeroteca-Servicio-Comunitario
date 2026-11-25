"""Ejecuta servicios fuera del hilo gráfico conservando los contratos existentes.

Las lecturas de pantalla entregan resultados por callbacks sin espera modal.
Las acciones existentes conservan su exclusión y sus transacciones. Cada
trabajador abre su conexión y solo el hilo principal modifica widgets.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext, contextmanager
import sqlite3
import tkinter as tk
import gc
from tkinter import ttk

from database.maintenance import database_guard


def materializar(valor):
    """Desvincula filas SQLite del hilo que creó la conexión de origen."""
    if isinstance(valor, sqlite3.Row):
        return dict(valor)
    if isinstance(valor, list):
        return [materializar(elemento) for elemento in valor]
    if isinstance(valor, tuple) and hasattr(valor, '_fields'):
        # Conserva ResultadoRegistro y su atributo recovery_code al cruzar hilos.
        return type(valor)(*(materializar(elemento) for elemento in valor))
    if isinstance(valor, tuple):
        return tuple(materializar(elemento) for elemento in valor)
    if isinstance(valor, dict):
        return {clave: materializar(elemento) for clave, elemento in valor.items()}
    return valor


class ServicioEnSegundoPlano:
    """Conserva los nombres de API y delega cada operación al coordinador."""

    def __init__(self, coordinador, nombre):
        """Identifica el grupo de servicios sin abrir conexiones adicionales."""
        self.coordinador, self.nombre = coordinador, nombre

    def __getattr__(self, nombre):
        """Expone atributos y envuelve métodos sin transportar widgets al trabajador."""
        original = getattr(getattr(self.coordinador.original, self.nombre), nombre)
        if not callable(original):
            return original

        def ejecutar(*argumentos, **opciones):
            """Invoca el método solicitado con una conexión propiedad del trabajador."""
            return self.coordinador.ejecutar(self.nombre, nombre, argumentos, opciones)
        return ejecutar


class ServiciosDeInterfaz:
    """Adapta los servicios de negocio a una interfaz Tkinter que sigue respondiendo."""

    def __init__(self, ventana, servicios):
        """Crea un trabajador único y conserva la conexión original en su hilo."""
        self.ventana, self.original = ventana, servicios
        self.ejecutor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='perri-servicios')
        self.cerrado = False
        self.lectores = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hemeroteca-lecturas")
        self.autorizaciones = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hemeroteca-acceso")
        self._trabajos = 0
        self._restaurar_gc = False
        self._nivel_interfaz = 0
        for nombre in ('access', 'audit', 'auth', 'recovery', 'periodicos', 'requests', 'users', 'backups', 'reports', 'network', 'client'):
            if getattr(servicios, nombre, None) is not None:
                setattr(self, nombre, ServicioEnSegundoPlano(self, nombre))

    def __getattr__(self, nombre):
        """Conserva indicadores de modo y rutas utilizados por las vistas actuales."""
        return getattr(self.original, nombre)

    def cerrar(self):
        """Libera el ejecutor y cierra los servicios originales una sola vez."""
        if self.cerrado:
            return
        self.cerrado = True
        self.lectores.shutdown(wait=False, cancel_futures=True)
        self.autorizaciones.shutdown(wait=False, cancel_futures=True)
        self.ejecutor.shutdown(wait=False, cancel_futures=True)
        self.original.close()
    # Alias del contrato anterior: conserva integraciones y llamadas RPC.
    close = cerrar

    @contextmanager
    def agrupar_interfaz(self):
        """Agrupa la recolección en el hilo gráfico sin omitir ninguna operación."""
        exterior = self._nivel_interfaz == 0
        automatica = gc.isenabled()
        if exterior:
            gc.disable()
            gc.collect()
        self._nivel_interfaz += 1
        try:
            yield
        finally:
            self._nivel_interfaz -= 1
            if exterior:
                gc.collect()
                if automatica:
                    if self._trabajos:
                        self._restaurar_gc = True
                    else:
                        gc.enable()

    def ejecutar(self, grupo, metodo, argumentos, opciones):
        """Espera un resultado procesando eventos, con exclusión de nuevas acciones."""
        if self.cerrado:
            raise ValueError('Los servicios ya se cerraron.')
        if getattr(self.ventana, '_servicios_ocupados', False):
            raise ValueError('Espera a que termine la operación actual.')
        self.ventana._servicios_ocupados = True
        argumentos = tuple(self if valor is self else materializar(valor) for valor in argumentos)
        opciones = materializar(opciones)
        indicador = f'perri_tarea_{id(self)}'
        self.ventana.setvar(indicador, False)
        progreso = None
        barra = None
        anterior = self.ventana.grab_current()

        def mostrar():
            """Muestra progreso solo si la tarea tarda lo suficiente para percibirse."""
            nonlocal progreso, barra
            if not futuro.done():
                progreso = tk.Toplevel(self.ventana)
                progreso.withdraw()
                progreso.title('Hemeroteca · Procesando')
                progreso.transient(self.ventana)
                progreso.resizable(False, False)
                progreso.protocol('WM_DELETE_WINDOW', lambda: None)
                ttk.Label(progreso, text='Procesando la operación…', padding=24).pack()
                barra = ttk.Progressbar(progreso, mode='indeterminate', length=280)
                barra.pack(padx=24, pady=(0, 24))
                progreso.deiconify()
                progreso.grab_set()
                barra.start(15)

        def trabajar():
            """Conserva exclusión y transacciones de las acciones existentes."""
            def operar(temporal):
                """Resuelve el servicio y sustituye el coordinador por su contexto local."""
                destino = self.original.network if grupo == 'network' else temporal.client if grupo == 'client' else getattr(temporal, grupo)
                nuevos = tuple(temporal if valor is self else valor for valor in argumentos)
                if emparejamiento:
                    return destino.registrar_autorizacion(*nuevos, **opciones)
                return getattr(destino, metodo)(*nuevos, **opciones)
            emparejamiento = grupo == 'network' and metodo in ('approve_computer', 'aprobar_computadora')
            resultado = self._con_servicios(operar, grupo, metodo)
            # El cliente llama a /device/verify antes de contestar. La barrera ya está libre.
            return resultado() if emparejamiento else resultado

        self._iniciar_trabajo()
        futuro = self.ejecutor.submit(trabajar)

        def recibir():
            """Notifica desde Tk que el resultado del trabajador ya está disponible."""
            if futuro.done():
                self.ventana.setvar(indicador, True)
            else:
                self.ventana.after(25, recibir)

        aviso = self.ventana.after(250, mostrar)
        self.ventana.after(10, recibir)
        try:
            self.ventana.wait_variable(indicador)
            return futuro.result()
        finally:
            self.ventana.after_cancel(aviso)
            if progreso is not None:
                barra.stop()
                progreso.destroy()
                if anterior is not None and anterior.winfo_exists():
                    anterior.grab_set()
            self.ventana._servicios_ocupados = False
            self.ventana.tk.call('unset', indicador)
            self._terminar_trabajo()

    def _con_servicios(self, operacion, grupo='', metodo=''):
        """Abre y cierra conexiones en su propio hilo; nunca entrega widgets al trabajador."""
        temporal = None
        remoto = self.original.read_only
        try:
            if remoto:
                from network.client import RemoteClient, RemoteServices
                cliente = RemoteClient(dict(self.original.client.settings), self.original.network)
                cliente.token = self.original.client.token
                temporal = RemoteServices(cliente, self.original.network)
                proteccion = nullcontext()
            else:
                from services.container import create_services
                ruta = self.original.backups.database
                proteccion = database_guard(ruta, exclusive=(grupo in ('backups', 'network') or metodo == 'formatear_aplicacion'))
            with proteccion:
                if not remoto:
                    temporal = create_services(ruta, node_id=self.original.access.node_id, initialize=False)
                    temporal.network = self.original.network
                    temporal.backups.settings_path = self.original.backups.settings_path
                    temporal.backups.network_path = self.original.backups.network_path
                return materializar(operacion(temporal))
        finally:
            if temporal is not None:
                if remoto:
                    # No cerrar RemoteServices: logout invalidaría el token compartido.
                    if grupo:
                        self.original.client.token = temporal.client.token
                        self.original.client.settings = dict(temporal.client.settings)
                else:
                    temporal.close()


    def _iniciar_trabajo(self):
        """Impide que el recolector destruya objetos Tcl desde un hilo de datos."""
        self._restaurar_gc = self._restaurar_gc or gc.isenabled()
        gc.disable()
        self._trabajos += 1

    def _terminar_trabajo(self):
        """Recoge ciclos en Tk cuando terminan los trabajos concurrentes."""
        self._trabajos -= 1
        if not self._trabajos and not self._nivel_interfaz:
            gc.collect()
            if self._restaurar_gc and not self._nivel_interfaz:
                gc.enable()
                self._restaurar_gc = False

    def consulta(self, grupo, metodo, *argumentos, **opciones):
        """Captura valores de filtros en Tk; el descriptor no contiene controles."""
        from copy import deepcopy
        return (grupo, metodo, deepcopy(materializar(argumentos)), deepcopy(materializar(opciones)))

    def leer_async(self, consultas, recibir, fallar):
        """Ejecuta un lote de lecturas sin espera modal y entrega la respuesta en Tk."""
        if self.cerrado:
            raise ValueError('Los servicios ya se cerraron.')
        def operar(servicios):
            """Ejecuta el lote con una conexión propia y las validaciones de cada servicio."""
            return [getattr(getattr(servicios, grupo), metodo)(*args, **kw)
                    for grupo, metodo, args, kw in consultas]
        self._iniciar_trabajo()
        # Una búsqueda lenta no debe ocupar el trabajador que autoriza navegar.
        ejecutor = self.autorizaciones if consultas and all(c[0] == 'access' for c in consultas) else self.lectores
        futuro = ejecutor.submit(self._con_servicios, operar)
        def revisar():
            """Recibe resultados sin procesar bucles de eventos anidados."""
            if not futuro.done():
                self.ventana.after(20, revisar)
                return
            self._terminar_trabajo()
            if self.cerrado or futuro.cancelled():
                return
            try:
                datos = futuro.result()
            except Exception as excepcion:
                fallar(excepcion)
            else:
                recibir(datos)
        self.ventana.after(20, revisar)
        return futuro
