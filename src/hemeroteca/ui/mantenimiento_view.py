"""Confirmación explícita del reinicio de datos, exclusiva del maestro local."""
from tkinter import messagebox


class VistaMantenimiento:
    """Explica el alcance del formateo antes de solicitar credenciales y confirmación."""

    def _formatear_aplicacion(self):
        """Ofrece el borrado total de la base y de los equipos vinculados con respaldo previo."""
        if not self._require_access(master=True, action='Abrir formateo') or self.services.read_only:
            return
        ventana, cuerpo, pie = self._credential_container('Formatear Hemeroteca')
        self._paragraph(cuerpo, 'Se borrarán todos los datos de la base: ejemplares, fechas sin publicación, solicitudes, permisos, auditoría, usuarios y también la cuenta maestra con su recuperación. Esta PC olvidará las computadoras conectadas y volverá al modo local. Se guardará una copia previa; los respaldos existentes se conservarán. Después deberás registrar un nuevo administrador maestro y conectar de nuevo las otras PC.', color='#A83D35').pack(fill='x', padx=18, pady=18)
        envoltura, clave = self._entry(cuerpo, 'Tu contraseña actual de maestro', '', show='•')
        envoltura.pack(fill='x', padx=18, pady=12)
        envoltura, confirmacion = self._entry(cuerpo, 'Escribe FORMATEAR HEMEROTECA para confirmar', '')
        envoltura.pack(fill='x', padx=18, pady=12)
        error = self._paragraph(cuerpo, '', color='#A83D35')
        error.pack(fill='x', padx=18, pady=12)
        def ejecutar():
            """Pide confirmación final y delega el borrado al servicio autorizado."""
            if confirmacion.get() != 'FORMATEAR HEMEROTECA':
                error.configure(text='Escribe exactamente FORMATEAR HEMEROTECA.')
                return
            if not messagebox.askyesno('Confirmar formateo', '¿Borrar toda la base, incluida la cuenta maestra, y olvidar las computadoras conectadas?', parent=ventana):
                return
            try:
                copia = self.services.users.formatear_aplicacion(self.user, clave.get(), confirmacion.get())
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            self.services.original.network.reiniciar_tras_formateo()
            ventana.destroy()
            self._restart_services()
            messagebox.showinfo('Hemeroteca', f'La base quedó vacía y las computadoras se desvincularon. Registra un nuevo administrador maestro para comenzar.\n\nCopia de seguridad previa:\n{copia}', parent=self)
        self._button(pie, 'Formatear aplicación', ejecutar, 'danger', width=190).pack(side='right', padx=18, pady=14)
        self._button(pie, 'Cancelar', ventana.destroy, 'secondary').pack(side='left', padx=18, pady=14)
