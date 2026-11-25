# Hemeroteca 2.0.0

Esta versión conserva las reglas de la hemeroteca y mejora su implementación.
La versión del programa es 2.0.0; la versión del esquema SQLite es 5.

## Organización declarativa y nombres

`config/declaraciones.py` describe campos del formulario y páginas disponibles.
Los widgets se construyen a partir de esas declaraciones. Los servicios siguen
separados de Tkinter para permitir pruebas y funcionamiento por red.

Las implementaciones tienen nombres en español, así como sus variables locales
y documentación. Los nombres anteriores aparecen como alias comentados. Las
firmas públicas, columnas SQLite, claves JSON y opciones de librerías mantienen
su contrato original. Traducir esas cadenas rompería la compatibilidad con los
datos y la comunicación. Los métodos especiales de Python conservan sus nombres.

## Respuesta de la interfaz

`ui/tareas.py` adapta los servicios a un trabajador único por ventana. Cada tarea
crea y cierra su conexión SQLite en el propio trabajador; nunca transporta un
widget al hilo de servicios. Las filas se convierten en estructuras de datos.
La espera modal de Tcl/Tk procesa eventos y temporizadores; tras 250 ms muestra
progreso. Durante una operación no se admite un segundo envío ni el cierre de
la ventana principal, para impedir que una escritura quede sin respuesta visible.

La recolección de ciclos se realiza en el hilo gráfico alrededor de estas tareas
para que los destructores de variables Tcl no se ejecuten desde el trabajador.
Las exportaciones PDF conservan su patrón de cola e hilo independiente.

## Consultas y contexto

Catálogo, fechas sin publicación, usuarios, solicitudes, auditoría y eliminados
aplican filtros y paginación en SQL. Los servicios antiguos de listado se mantienen
para compatibilidad; las vistas nuevas utilizan las consultas paginadas.
Los filtros conservan comparación Unicode con `casefold`, mediante funciones SQL
registradas en cada conexión. Auditoría interpreta tanto fechas históricas como ISO.

La ventana recuerda filtros por usuario y vista, página y fila seleccionada.
Un cambio de filtros reinicia las páginas correspondientes. Un cambio de permisos
no destruye un formulario abierto: cada guardado vuelve a autorizar en el servidor.
Los fallos transitorios de conectividad conservan la pantalla y la identidad local.

## Integridad y mantenimiento

El esquema 5 agrega `issues.revision` e índices para activos, fechas, periodos y
solicitudes. La migración de archivo crea primero una copia como la versión anterior.
El formulario transmite la revisión leída y una edición obsoleta se rechaza.
Los clientes anteriores que no transmiten revisión conservan su contrato; por ello
se debe actualizar el conjunto de equipos para obtener esta protección completa.

`database/barrera.py` coordina operaciones compartidas y mantenimiento exclusivo.
En Windows utiliza `LockFileEx`; en otros sistemas, `flock`. También coordina hilos
del proceso y permite reentrada compatible. La exclusividad debe pedirse al iniciar
una operación: no se permite ascender un acceso compartido, evitando interbloqueos.
SQLite sigue serializando escritores. No se activó WAL ni se cambió el motor.

Las anotaciones equivocadas de días sin publicación pueden anularse con permiso
de registro y confirmación. Auditoría conserva la fecha, periódico y nota anterior.
Esto resuelve el bloqueo que impedía registrar o restaurar ejemplares de esa fecha.

## Red, respaldos y datos anteriores

TLS, huella, firmas por equipo, nonces y sesiones se conservan. La nueva consulta
de estado agrupa usuario, permisos y requisitos. Las operaciones nuevas se incluyen
explícitamente en la lista RPC permitida y autorizan de nuevo en el servidor.
Las consultas habituales dejan de tomar el bloqueo exclusivo global de mantenimiento.

La restauración acepta esquemas 3, 4 y 5, reconstruye tablas conocidas y retira
sesiones y dispositivos. Los datos de Hemeroteca usan una carpeta independiente; la
importación opcional lee la anterior en modo de solo lectura y rechaza sobrescribir
el destino. Deben configurarse de nuevo los respaldos y equipos autorizados.

## Decisiones para conservar funcionalidades

Se mantuvieron perfiles, autorregistro regular, preguntas de seguridad, códigos,
estados, títulos y límites de fechas. No se cambió a un servidor de Windows ni se
añadió escritura sin conexión. La principal sigue necesitando estar abierta para
atender consultas LAN, como antes. Desvincular el servidor de la ventana y cambiar
el vocabulario de estados son evoluciones de producto y despliegue, no correcciones
aplicadas silenciosamente a esta entrega.

El PDF general todavía depende del volumen a exportar y conserva el límite de
64 MiB. Cancelar descarga no detiene un trabajo remoto que ya comenzó. No se
afirma escalabilidad ilimitada ni equivalencia de rendimiento para cualquier red.

## Verificación

`verificar_version.py` compila los fuentes y exige documentación en toda función
y clase. Después ejecuta la suite unitaria, pantallas reales de Tkinter y la
integración TLS/SQLite/PDF/respaldo cifrado. Las pruebas usan rutas temporales.

`VERIFICACION.json` es el resultado de la entrega. Los archivos de texto asociados
conservan las salidas completas; los resultados de interfaz e integración detallan
los recorridos probados. La integración incluye exclusión entre procesos distintos.

La entrega es una carpeta de fuentes ejecutables con recursos y lanzadores. No
incluye datos personales, identidades de equipos, entornos copiados o ejecutables
históricos del instalador. En esta PC el lanzador puede usar el intérprete existente;
`Preparar_Windows.cmd` permite preparar un entorno propio.
