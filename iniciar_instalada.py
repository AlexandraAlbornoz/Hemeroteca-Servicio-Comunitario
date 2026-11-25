"""Entrada de la instalación Windows con registro local de errores de inicio."""

import contextlib
import logging
import os
import sys
from pathlib import Path


def ejecutar():
    'Abre la aplicación y registra fallos de inicio en la carpeta de Hemeroteca.'
    base = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    os.chdir(base)
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Hemeroteca.2.4')
        from config.settings import DATA_DIR
        private = DATA_DIR.parent
    else:
        private = base / 'data'
    logs = private / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    log_path = logs / 'aplicacion.log'
    logging.basicConfig(filename=log_path, encoding='utf-8', level=logging.WARNING,
                        format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    with log_path.open('a', encoding='utf-8', buffering=1) as errors, contextlib.redirect_stderr(errors):
        try:
            from main import main
            main()
        except Exception:
            logging.exception('No se pudo abrir Hemeroteca')
            try:
                import tkinter as tk
                from tkinter import messagebox
                root = tk.Tk()
                root.withdraw()
                messagebox.showerror('Hemeroteca', f'No se pudo abrir la aplicación.\n\nConsulta el registro:\n{log_path}', parent=root)
                root.destroy()
            except Exception:
                pass
            raise SystemExit(1)
# Alias del contrato anterior: conserva integraciones y llamadas RPC.
run = ejecutar


if __name__ == '__main__':
    if '--backup-worker' in sys.argv:
        sys.argv.remove('--backup-worker')
        from backup_worker import main as ejecutar_respaldo
        raise SystemExit(ejecutar_respaldo())
    if '--verificar-instalacion' in sys.argv:
        from utils.verificacion_instalacion import verificar
        raise SystemExit(verificar())
    run()
