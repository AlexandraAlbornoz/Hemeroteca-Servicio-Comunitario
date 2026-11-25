# Hemeroteca 2.3.0: interfaz y carga de datos

Esta versión separa la construcción de las ocho vistas internas de sus consultas iniciales. Conserva el esquema de la base, los contratos de los servicios y las funciones de registro, edición, recuperación, permisos, reportes y respaldos.

## Flujo de navegación

1. El menú responde y muestra el destino con un indicador dentro de la sección.
2. Un trabajador reservado comprueba la sesión y el permiso de acceso. No se muestran datos protegidos antes de autorizar la vista.
3. Tk construye los campos, botones y tablas vacías. Durante esta construcción se reutiliza la instantánea de permisos recién validada.
4. Trabajadores independientes consultan los datos iniciales. Las tablas, contadores y opciones se actualizan al recibirlos. No se abre un diálogo modal para estas lecturas.
5. Buscar, filtrar, paginar o elegir otra sección inicia la consulta correspondiente. Generar PDF, guardar, eliminar y restaurar conservan sus acciones explícitas y verificaciones.

La consulta inicial de registros se mantiene para conservar el comportamiento anterior. No se genera un PDF ni se ejecuta una operación de mantenimiento al abrir su pantalla. El estado detallado de respaldos se consulta al entrar a Respaldos, en lugar de consultarlo también al reconstruir el marco principal.

## Responsabilidades y reutilización

- `ui/tareas.py`: un único contexto de conexión para acciones y lecturas, conexiones SQLite propias de cada trabajador, descriptores con valores de filtros, entrega de resultados en Tk y coordinación del recolector de memoria. Las acciones existentes conservan su exclusión y transacciones. Las autorizaciones de navegación disponen de un trabajador independiente de las búsquedas.
- `ui/carga.py`: indicador local, generación de vista y sesión, control de la última petición y cancelación de trabajos que aún no comenzaron.
- `ui/components.py`: tabla paginada común a consulta, catálogo, ausencias, auditoría, solicitudes, usuarios y eliminados. Al filtrar o paginar se conservan el Treeview, las barras y los botones; se sustituyen las filas. Las pantallas diferentes siguen teniendo sus propios controles, sin una caché global de formularios o permisos.
- Las vistas capturan los filtros en el hilo gráfico. Ningún trabajador llama a `Entry.get()`, crea controles ni modifica widgets.

Cada consulta y escritura sigue siendo autorizada por el servicio local o remoto. La instantánea de permisos utilizada para dibujar controles no concede permisos adicionales ni sustituye las verificaciones de las operaciones.

## Respuestas tardías y errores

Cada sección identifica la sesión, la generación de pantalla y la versión de su consulta. Si llega un resultado de otra pantalla, otra sesión o una búsqueda reemplazada, se descarta. Se cancela trabajo pendiente; una consulta que ya está ejecutándose puede terminar, pero no puede actualizar la vista abandonada. Los errores aparecen en la sección y las denegaciones sincronizan la sesión.

Cambiar de pestaña en Catálogo conserva sus controles y muestra únicamente la paginación de la sección activa. El cierre de la ventana invalida las entregas y espera de forma oculta a que terminen los lectores antes de destruir Tcl.

## Validación

Se utilizan exclusivamente bases ficticias temporales:

- 175 pruebas de regresión: aprobadas.
- Interfaz local: las ocho vistas, perfiles maestro, administrador regular y usuario regular, y rechazo de una vista no autorizada.
- Consulta demorada: tabla construida antes del resultado, temporizadores gráficos activos y navegación a Reportes sin esperar esa consulta.
- Respuesta tardía descartada, última búsqueda prevalece e invalidación de sesión.
- Reutilización de la misma tabla al pasar de ocho filas a las tres restantes.
- Dieciséis combinaciones de pantalla y tamaño de ventana: paginación visible, cambio de pestaña, conservación de página y barras retiradas al destruir sus tablas.
- Navegación durante una escritura lenta: un único guardado, último destino respetado y salida de sesión sin navegación pendiente.
- Cliente HTTPS contra servidor ficticio en esta misma computadora: navegación y carga diferida aprobadas.
- Registro y edición mediante formularios: guardado, validación, rechazo de duplicado y cierre de temporizador aprobados.
- Integración: RPC TLS, paginación remota, conflicto de edición, PDF, restauración cifrada, invalidación de equipos/sesiones y recuperación por preguntas aprobados.
- Formularios de recuperación: código mostrado tras registro, recuperación por ambas vías y rotación del código aprobados. El cierre de los escenarios espera a sus lectores antes de retirar la base temporal.

Los resultados exactos se incluyen en los archivos `RESULTADO_CARGA_ASINCRONA.json`, `RESULTADO_CARGA_REMOTA.json`, `RESULTADO_GUARDAR_EJEMPLAR.json` y en las verificaciones de regresión e integración. La medición de retorno de navegación representa la respuesta del controlador, no el tiempo total de descarga ni una promesa de carga instantánea en cualquier equipo.

La suite histórica emite algunos avisos de temporizadores de CustomTkinter al destruir ventanas de prueba; termina con 175 pruebas aprobadas. Las pruebas nuevas registraron cero excepciones de callbacks de Tk.

## Alcance de la entrega

Se entrega código fuente sin empaquetar. No se instala sobre la versión actual ni se modifica la carpeta jamon original. Tampoco se copian bases de datos, cuentas, certificados, claves privadas ni configuraciones de conexión. No se ha comprobado la conexión entre las dos computadoras físicas: la validación cliente-servidor de esta entrega es simulada mediante HTTPS local. No se modificó la VPN.

El inicio de sesión y los diálogos de acciones conservan sus verificaciones y flujos existentes; esta refactorización cambia la carga y navegación de las vistas internas, no el protocolo de autenticación ni el esquema de datos.
