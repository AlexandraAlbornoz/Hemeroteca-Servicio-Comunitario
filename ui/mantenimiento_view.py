"""Confirmación explícita del reinicio de datos, exclusiva del maestro local."""
from tkinter import messagebox


class VistaMantenimiento:
    """Explica el alcance del formateo antes de solicitar credenciales y confirmación."""

    def _formatear_aplicacion(self):
        """Ofrece el borrado de datos operativos con respaldo obligatorio previo."""
        if not self._require_access(master=True, action='Abrir formateo') or self.services.read_only:
            return
        ventana, cuerpo, pie = self._credential_container('Formatear Hemeroteca')
        self._paragraph(cuerpo, 'Se borrarán los ejemplares, las fechas sin publicación, las solicitudes, los permisos y las demás cuentas. Tu cuenta maestra, sus medios de recuperación, la configuración de red y el historial de auditoría se conservarán. Se guardará una copia de seguridad antes del borrado.', color='#A83D35').pack(fill='x', padx=18, pady=18)
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
            if not messagebox.askyesno('Confirmar formateo', '¿Borrar los datos indicados y comenzar de nuevo? Esta operación cerrará las sesiones activas.', parent=ventana):
                return
            try:
                copia = self.services.users.formatear_aplicacion(self.user, clave.get(), confirmacion.get())
            except ValueError as excepcion:
                error.configure(text=str(excepcion))
                return
            ventana.destroy()
            self.show_login()
            messagebox.showinfo('Hemeroteca', f'Los datos se reiniciaron. Tu cuenta maestra se conserva.\n\nCopia de seguridad:\n{copia}', parent=self)
        self._button(pie, 'Formatear aplicación', ejecutar, 'danger', width=190).pack(side='right', padx=18, pady=14)
        self._button(pie, 'Cancelar', ventana.destroy, 'secondary').pack(side='left', padx=18, pady=14)
