# Respaldos diarios y reportes PDF

## Qué archivo utilizar

| Archivo | Para qué sirve | Quién puede generarlo o utilizarlo |
| --- | --- | --- |
| `.hmbackup` | Llevarse una copia completa de la base y restaurarla después. | Administrador maestro, desde la PC principal. |
| `.pdf` de ejemplares | Consultar o imprimir los ejemplares activos seleccionados. | Cuentas con **Exportar ejemplares a PDF**. |
| `.pdf` general | Consultar o imprimir el contenido operativo del sistema. | Cuentas con **Exportar base de datos a PDF**. |

El PDF no sirve para restaurar. El respaldo no es un documento editable ni una
base SQLite que pueda abrirse directamente con un editor.

## 1. Preparar la actualización en Windows

1. Cierra Hemeroteca en la PC principal y en las computadoras de consulta.
2. Copia el código actualizado, incluido `backup_worker.py` y
   `Programar_Respaldos_Windows.ps1`.
3. Ejecuta **Preparar_Windows.cmd** en cada PC para instalar las dependencias
   actualizadas. ReportLab es la biblioteca que genera los PDF.
4. Abre **Iniciar_Hemeroteca.cmd**.

Esta funcionalidad no crea cuentas ni cambia las contraseñas existentes. Los
permisos nuevos se guardan en la tabla `grants`; no requiere nuevas tablas.

## 2. Activar las copias diarias

Entra como maestro en la PC que contiene la base:

1. Abre **Respaldos de seguridad** en el menú lateral. El menú se puede desplazar
   verticalmente en pantallas pequeñas.
2. Pulsa **Configurar copias diarias**.
3. Elige la carpeta de destino. La carpeta inicial es `data/respaldos/`.
4. Selecciona la hora y los minutos. La hora predeterminada es **18:00**, según
   el reloj de esa PC.
5. Crea y repite una **clave para los respaldos**, de 12 a 256 caracteres.
   Es una clave propia de los archivos; no cambia tu contraseña de usuario.
6. Anota esa clave en un lugar seguro fuera de la computadora y marca la
   confirmación. Sin ella, los respaldos no pueden restaurarse.
7. Confirma tu contraseña actual de maestro y pulsa **Activar y crear primera
   copia**.

Se crea una copia inicial inmediatamente. Después, la aplicación revisa cada
minuto si falta la copia diaria. También lo comprueba al iniciar.

En Windows se registra una tarea en el **Programador de tareas**, para la cuenta
de Windows que configuró las copias. Puede ejecutarse con Hemeroteca cerrada,
siempre que esa cuenta tenga una sesión Windows iniciada y la PC esté encendida.
También tiene un disparador al iniciar la sesión Windows. No solicita ni guarda
la contraseña de Windows. Si una política impide registrar la tarea, la pantalla
lo indica y ofrece **Reintentar programación de Windows**; mientras tanto, la
automatización funciona con Hemeroteca abierta.

Una computadora apagada o sin acceso a la carpeta elegida no puede crear la
copia. Se intenta la copia pendiente al recuperar esas condiciones. No se
inventan copias de días pasados: la copia contiene los datos disponibles cuando
realmente se crea.

Los respaldos se conservan sin eliminación automática. Revisa el espacio de la
carpeta. Si eliges una memoria USB como destino diario, debe estar conectada y
conservar su letra de unidad; otra opción es guardar localmente y exportar una
copia a USB periódicamente.

### Estado y acciones

- **Crear respaldo ahora:** genera una copia adicional y pide tu contraseña de
  maestro. No reemplaza las copias anteriores.
- **Desactivar copias diarias:** detiene la automatización y conserva los archivos
  ya creados.
- **Configurar copias diarias** otra vez permite cambiar hora, carpeta o clave.
  Los archivos anteriores mantienen la clave original; no se vuelven a cifrar.
- Si hay un error de copia o programación, se muestra en esta pantalla y se
  avisa al maestro al abrir su sesión.

## 3. Llevarse una copia

1. En **Respaldos de seguridad**, selecciona un archivo de la lista.
2. Pulsa **Guardar en USB u otra carpeta**.
3. Elige la memoria o carpeta externa y guarda el archivo con extensión
   `.hmbackup`.
4. Conserva la clave por separado. Puedes transportar este archivo a otra PC
   que tenga una versión compatible de Hemeroteca.

Ejemplo: `hemeroteca-diario-20261015-180000-a1b2c3.hmbackup`.

El archivo usa cifrado autenticado **AES-256-GCM** y una clave derivada mediante
**scrypt**. El contenido y los metadatos se validan juntos. Si se alteran, la
restauración se rechaza. La aplicación no ofrece herramientas para editarlo.
Esto detecta alteraciones; ningún formato puede impedir físicamente que alguien
reemplace o borre un archivo al que tenga acceso.

En Windows, la clave necesaria para las copias automáticas se guarda protegida
con **DPAPI**, vinculada a la cuenta Windows que las configuró. El archivo
portable no depende de esa cuenta: se restaura con la clave del respaldo. No
copies `backup-settings.json` para habilitar otra PC; configúrala desde la
aplicación. En el entorno de desarrollo macOS/Linux, la clave local se protege
con permisos de archivo, sin tarea automática de Windows.

## 4. Restaurar una copia

La restauración **reemplaza** la base actual; no mezcla dos colecciones.

1. En la PC principal, inicia sesión como maestro.
2. Abre **Respaldos de seguridad → Seleccionar respaldo para restaurar**.
3. Selecciona el `.hmbackup` de la carpeta o memoria externa.
4. Escribe la clave con la que se creó y pulsa **Revisar respaldo sin cambiar
   los datos**.
5. Comprueba la fecha, los totales y el documento del administrador guardado.
6. Confirma tu contraseña de maestro actual y escribe **RESTAURAR**.
7. Pulsa **Restaurar y cerrar las sesiones**.

Antes de aplicar los datos se guarda automáticamente una copia cifrada del
estado actual en `data/respaldos/`, con `antes-de-restaurar` en el nombre. Esa
copia utiliza la **misma clave del respaldo que acabas de abrir**.

Al finalizar:

- Se restauran cuentas y contraseñas tal como estaban en el respaldo, preguntas,
  códigos, permisos, solicitudes, ejemplares, fechas sin publicación y auditoría.
- Debes entrar con las credenciales vigentes en la fecha del respaldo. Un cambio
  de contraseña posterior a esa fecha no está incluido.
- Se invalidan sesiones anteriores. No se importan sesiones, intentos de acceso,
  autorizaciones de equipos ni traslados pendientes del pasado.
- La PC actual mantiene su configuración local y será la que contiene la base.
  El maestro debe volver a autorizar las computadoras de consulta.

Para restaurar en una **PC nueva**, prepara la aplicación, registra primero un
administrador maestro temporal y utiliza su sesión para importar el archivo.
La restauración reemplazará también esa cuenta temporal por las cuentas del
respaldo. Si la PC va a sustituir al servidor anterior, deja de utilizar el
servidor anterior antes de autorizar los clientes en el nuevo.

Se comprueba el formato, la autenticación criptográfica, la versión, la
integridad SQLite, las columnas conocidas, las relaciones y la existencia de un
maestro activo. Se reconstruye el esquema desde el código de la aplicación;
no se ejecutan disparadores ni instrucciones SQL procedentes del archivo.
El límite de la versión actual es **256 MiB de base de datos** por respaldo.

Hemeroteca 1.0.4 genera respaldos con esquema 4 y admite restaurar los de esquema
3 de las entregas anteriores. Al importar uno antiguo conserva los accesos
de sus administradores. Los respaldos nuevos conservan también la marca de
permisos administrados de las cuentas creadas desde 1.0.4.

## 5. Otorgar permisos para PDF

Desde la PC principal, el maestro abre:

**Usuarios → seleccionar persona → Gestionar cuenta → Configurar permisos de
reportes PDF**.

Marca o desmarca:

- **Exportar ejemplares a PDF:** todos los ejemplares activos o una selección.
- **Exportar base de datos a PDF:** contenido operativo general, incluidas
  cuentas y auditoría. Puede contener datos personales.

Pulsa **Guardar permisos PDF**. Los permisos son independientes y el maestro
los tiene incluidos en su perfil. También pueden solicitarse mediante
**Solicitudes de acceso**, desde la PC principal. Las cuentas inactivas no pueden
recibir nuevos permisos.

El servidor comprueba el permiso al generar y al entregar el PDF. La interfaz
lo comprueba de nuevo antes de guardarlo. Revocar un permiso impide nuevas
exportaciones; no borra documentos que una persona ya hubiera descargado.

## 6. Generar un reporte

### Ejemplares filtrados

En **Consulta de periódicos**, aplica los filtros con **Buscar** y pulsa
**Guardar resultado en PDF**. En **Catálogo de periódicos**, usa **Filtrar
catálogo** y después el mismo botón. El documento refleja los filtros aplicados
al resultado, aunque después cambies un campo sin volver a buscar.

También puedes abrir **Reportes PDF**, elegir periódico, tipo, fecha de
publicación y periodo de registro, y pulsar **Guardar PDF de ejemplares**.
Con **Todos** se exportan todos los ejemplares activos. La opción de últimos
cinco respeta ese límite; las otras incluyen todos los resultados del periodo.

El PDF incluye todas las páginas del resultado, ordenadas del registro más
reciente al más antiguo, con edición, número, ubicación, estado y datos del
registro. Tiene encabezados, tablas que continúan y páginas numeradas.

### Contenido general

En **Reportes PDF**, pulsa **Guardar PDF general**. Incluye:

1. Ejemplares activos y eliminados.
2. Fechas sin publicación.
3. Cuentas: nombre, documento, perfil, estado y fecha de registro.
4. Permisos adicionales y solicitudes con sus respuestas.
5. Auditoría y datos visibles de las computadoras autorizadas.

No exporta contraseñas ni sus hashes, preguntas/respuestas de seguridad,
códigos ni sus hashes, sesiones, claves, certificados o secretos de traslado.
Las cuentas y registros personales requieren el permiso general explícito.

Elige dónde guardar el `.pdf`; puedes seleccionar una USB. Generar y descargar
un reporte desde una PC de consulta autorizada no modifica el inventario de la
principal. El evento se registra en auditoría. El límite de salida es **64 MiB**
por PDF; para colecciones mayores, utiliza filtros o un respaldo cifrado.

## Notas técnicas y documentación de referencia

- Copia consistente en caliente mediante
  [SQLite Connection.backup de Python](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup).
- [Cifrado autenticado AES-GCM](https://cryptography.io/en/stable/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM)
  y [derivación scrypt](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#scrypt).
- [Protección DPAPI de Windows](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).
- [Configuración de tareas de Windows](https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtasksettingsset).
- [Guía de generación PDF de ReportLab](https://www.reportlab.com/docs/reportlab-userguide.pdf).

El esquema actual es versión 4; se mantiene la lectura de respaldos de versión 3.
Los archivos privados nuevos se excluyen de Git:
respaldos `.hmbackup`, configuración con clave local y archivos de exclusión.
La API LAN expone solamente `reports.generate` de estas funciones; no expone
crear, configurar, descargar ni restaurar respaldos, ni conceder permisos.

La programación, DPAPI, restauración y presentación de PDF requieren validación
funcional en las computadoras Windows de destino. Esta entrega se revisó de
forma estática sin ejecutar restauraciones sobre la base real.
