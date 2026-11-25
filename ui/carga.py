"""Coordinación de lecturas: solo el hilo de Tk modifica controles."""
import customtkinter as ctk
from config.settings import RED, MUTED
from services.access_service import AccessDenied


class CargaDeVistas:
    """Descarta respuestas de vistas, sesiones y filtros que ya no están vigentes."""

    def _invalidar_cargas(self):
        """Invalida callbacks y cancela consultas que todavía no comenzaron."""
        self._generacion_vista = getattr(self, '_generacion_vista', 0) + 1
        for futuro in getattr(self, '_futuros_vista', []):
            futuro.cancel()
        self._futuros_vista = []

    def _cargar_seccion(self, padre, consultas, presentar, *, clave='datos', error=None):
        """Muestra progreso local, captura la sesión y entrega solo el último resultado."""
        generacion = getattr(self, '_generacion_vista', 0)
        usuario = (self.user['id'], self.user['password_version']) if self.user else None
        versiones = getattr(padre, '_versiones_carga', {})
        padre._versiones_carga = versiones
        versiones[clave] = versiones.get(clave, 0) + 1
        version = versiones[clave]
        indicadores = getattr(padre, '_indicadores_carga', {})
        padre._indicadores_carga = indicadores
        indicador = indicadores.get(clave)
        if indicador is None or not indicador.winfo_exists():
            indicador = ctk.CTkLabel(padre, text='', text_color=MUTED)
            if padre.grid_slaves():
                columnas, filas = padre.grid_size()
                indicador.grid(row=filas, column=0, columnspan=max(1, columnas), sticky='ew', padx=12, pady=4)
            else:
                indicador.pack(fill='x', padx=12, pady=4)
            indicadores[clave] = indicador
        indicador.configure(text='Cargando…', text_color=MUTED)

        def vigente():
            """Comprueba identidad, generación y existencia sin acceder desde el trabajador."""
            actual = (self.user['id'], self.user['password_version']) if self.user else None
            return (generacion == getattr(self, '_generacion_vista', 0)
                    and actual == usuario and padre.winfo_exists()
                    and versiones.get(clave) == version)

        def recibir(datos):
            """Actualiza controles únicamente cuando la petición todavía corresponde a la vista."""
            if vigente():
                indicador.configure(text='')
                presentar(datos)

        def fallar(excepcion):
            """Presenta errores en la sección y conserva la sincronización de permisos."""
            if vigente():
                indicador.configure(text=str(excepcion), text_color=RED)
                if error:
                    error(excepcion)
                if isinstance(excepcion, AccessDenied):
                    self.after_idle(self._sync_session)

        pendientes = getattr(padre, '_futuros_carga', {})
        padre._futuros_carga = pendientes
        if clave in pendientes:
            pendientes[clave].cancel()
        futuro = self.services.leer_async(consultas, recibir, fallar)
        pendientes[clave] = futuro
        self._futuros_vista = [f for f in getattr(self, '_futuros_vista', []) if not f.done()]
        self._futuros_vista.append(futuro)
        return futuro

    def _permisos_actuales(self):
        """Reutiliza permisos solo durante la construcción autorizada; las acciones revalidan."""
        contexto = getattr(self, '_contexto_construccion', None)
        if contexto is not None:
            return set(contexto)
        return set(self.services.access.permissions(self.user))
