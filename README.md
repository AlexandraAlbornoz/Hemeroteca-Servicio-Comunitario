# Hemeroteca

Aplicación de escritorio Python para catálogo de periódicos, usuarios, permisos,
solicitudes, auditoría, reportes PDF, respaldos y trabajo en red local.

Esta entrega contiene **código fuente sin empaquetar**, basado en la versión 2.4.0.
No incluye ejecutables, instaladores, cuentas ni bases de datos precargadas.

## Preparación y ejecución

Requisito de referencia: Python 3.13 con Tcl/Tk y pip, disponible como `python`.
Windows es la plataforma principal; los scripts de firewall y tareas programadas
son exclusivos de Windows. Descargue o clone el proyecto y abra PowerShell dentro
de la carpeta que contiene este README. Compruebe primero el intérprete:

```powershell
python --version
```

Debe mostrar **Python 3.13.x**. Cree el entorno eligiendo **una sola** opción:

Si `python` corresponde a 3.13:

```powershell
python -m venv .venv
```

Si `python` corresponde a otra versión, compruebe `py -3.13 --version`.
Si el lanzador encuentra Python 3.13, use:

```powershell
py -3.13 -m venv .venv
```

Si el lanzador no encuentra 3.13, instálelo o use la ruta completa de un Python 3.13
con Tcl/Tk y pip. En PowerShell una ruta entre comillas requiere `&`, por ejemplo:

```powershell
& 'C:\ruta\Python313\python.exe' -m venv .venv
```

Después de crear `.venv` con una de esas opciones, ejecute el bloque común:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\.venv\Scripts\python.exe -m pip check
```

La instalación de dependencias requiere acceso a Internet. Compruebe Tcl/Tk con el
mismo entorno que acaba de instalar:

```powershell
.\.venv\Scripts\python.exe -m tkinter
```

Debe abrir una ventana de demostración, que puede cerrar antes de iniciar Hemeroteca:

```powershell
.\.venv\Scripts\python.exe -m hemeroteca
```

No es necesario activar el entorno. Para usar la entrada alternativa ejecute
`.\.venv\Scripts\python.exe main.py`. La primera ejecución permite registrar al administrador
maestro. No hay una contraseña predeterminada. Para comprobar el inicio basta con
ver el formulario inicial; puede cerrar la ventana sin crear ninguna cuenta.
Al cerrar esa ventana debe regresar el control a PowerShell sin un traceback.

En desarrollo los datos quedan en `datos/` en la raíz del repositorio, excluida
de Git. Puede elegir otra carpeta con la variable `HEMEROTECA_DATA_DIR` antes de
iniciar. No se importa automáticamente la colección de una instalación anterior.

## Pruebas y datos de ejemplo

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m scripts.seed_hemeroteca
```

El segundo comando es opcional y agrega 100 ejemplares ficticios a la base de
desarrollo; no crea usuarios. Las pruebas de interfaz requieren una sesión gráfica.
Las pruebas manuales adicionales se ejecutan como módulos, por ejemplo:
`.\.venv\Scripts\python.exe -m tests.manual.pruebas_navegacion`.
La suite automatizada debe terminar con `OK`. Las pruebas de red utilizan
conexiones locales a `127.0.0.1`; el entorno debe permitirlas. No es necesario
configurar el firewall ni activar tareas programadas para esta comprobación.

## Organización

```text
src/hemeroteca/   Paquete de la aplicación
  config/        Configuración y declaraciones
  database/      Conexión, transacciones y esquema SQLite
  services/      Operaciones, permisos y reglas del negocio
  network/       Comunicación y coordinación de la red local
  ui/            Vistas, controles y tareas de interfaz
  utils/         Utilidades compartidas
  assets/        Imágenes e iconos
  resources/     Scripts Windows utilizados por la aplicación
tests/           Suite automatizada existente
tests/manual/    Escenarios manuales de interfaz e integración
scripts/         Importación y carga de datos ficticios
docs/            Arquitectura, desarrollo y validación
docs/historial/  Documentación original de referencia
.github/         Pruebas automáticas y plantillas de colaboración
```

Para contribuir, consulte [CONTRIBUTING.md](CONTRIBUTING.md).
Los controles de seguridad, comandos de auditoría, protección de la carpeta de
datos y ajustes pendientes de GitHub se explican en [docs/seguridad.md](docs/seguridad.md).
Los controles de cobertura, análisis estático, rendimiento y accesibilidad parcial
están en [docs/calidad.md](docs/calidad.md).
Los resultados de la revisión actual y sus límites están en
[docs/informe-calidad-seguridad.md](docs/informe-calidad-seguridad.md).
La ampliación más reciente de pruebas de red y respaldos está en
[docs/ampliacion-cobertura.md](docs/ampliacion-cobertura.md).
La revisión posterior de formularios y formato de archivos está en
[docs/cobertura-ui-formato.md](docs/cobertura-ui-formato.md).
La ampliación global más reciente, con pruebas de recuperación, red, usuarios,
reportes y descubrimiento, está en [docs/cobertura-global.md](docs/cobertura-global.md).
La revisión de inicio de sesión y servidor, con una nueva instalación limpia, está
en [docs/cobertura-login-servidor.md](docs/cobertura-login-servidor.md).
La ampliación posterior de solicitudes y periódicos está en
[docs/cobertura-solicitudes-periodicos.md](docs/cobertura-solicitudes-periodicos.md).
La revisión de ramas y errores asíncronos está en
[docs/cobertura-asincrona-ramas.md](docs/cobertura-asincrona-ramas.md).
La ampliación de módulos con menor cobertura está en
[docs/cobertura-modulos-pendientes.md](docs/cobertura-modulos-pendientes.md).
La revisión de usuarios, permisos y emparejamiento está en
[docs/cobertura-usuarios-permisos-red.md](docs/cobertura-usuarios-permisos-red.md).
La revisión posterior de ramas de autenticación, configuración y RPC está en
[docs/cobertura-ramas-restantes.md](docs/cobertura-ramas-restantes.md).
Última ampliación: [las catorce ramas pendientes](docs/cobertura-catorce-ramas.md).
Instalación limpia verificada con 702 pruebas: [informe y alcance](docs/comprobacion-copia-limpia-702.md).
Antes de usar datos reales en Windows, aplique la protección de esa carpeta con
la herramienta documentada. La base SQLite no incorpora cifrado completo.
La documentación vigente está en [docs/desarrollo.md](docs/desarrollo.md) y
[docs/arquitectura.md](docs/arquitectura.md). Los documentos de `docs/historial/`
pueden mencionar rutas, instaladores y resultados correspondientes al proyecto
anterior; no son instrucciones para esta distribución.

Se conserva el archivo LICENSE original con el texto GNU GPL v3.
Antes de publicar, el responsable debe comprobar que cuenta con los derechos
necesarios sobre el código, las imágenes y las marcas incluidas.

Guía paso a paso de publicación y activación de colaboración y seguridad: [publicar en GitHub](docs/publicar-en-github.md).

Última revisión de distribución: [contenido del ZIP y alcance](docs/revision-final-zip.md).
