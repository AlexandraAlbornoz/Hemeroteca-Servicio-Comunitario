# Instalar Hemeroteca - Hemeroteca en Windows

## Archivo que debes llevar

**Hemeroteca-Hemeroteca-Setup-1.0.5-x64.exe** es el instalador completo. Copia ese
archivo a la PC Windows y ábrelo con doble clic. No necesitas llevar la carpeta
del código ni compilar nada.

Requiere **Windows 10 u 11 x64**, para procesadores Intel o AMD. El paquete
incluye Python 3.13.13, Tcl/Tk y todas las bibliotecas para interfaz, red local,
respaldos cifrados y PDF. La preparación utiliza los archivos incluidos sin
descargar dependencias desde internet. Si ya hay Python 3.13 x64 con Tcl/Tk,
lo aprovecha; en caso contrario, prepara Python para la cuenta Windows actual.

## Pasos

1. Copia y abre el `.exe` en la computadora Windows.
2. Confirma la instalación y espera a que termine la preparación.
3. Se crean accesos **Hemeroteca - Hemeroteca** en el Escritorio y el menú Inicio.
4. El programa se abre al finalizar.
5. En la PC principal, registra al administrador y guarda su código de
   recuperación. En las demás, utiliza **Preparar PC de consulta** y autorízalas
   desde la principal siguiendo [la guía de red](RED_LOCAL.md).
6. El maestro puede configurar las copias diarias en **Respaldos de seguridad**
   y otorgar los permisos de PDF desde **Usuarios**.

El instalador inicia con una base nueva si esta copia Hemeroteca no tenía datos.
No incluye cuentas, bases, respaldos, claves de recuperación ni certificados
de la computadora de desarrollo. No requiere cuenta ni acceso a GitHub.

Windows puede mostrar un aviso porque esta versión de prueba no está firmada
digitalmente. La ejecución en Windows está pendiente de validación en la PC
de destino; el archivo se generó desde macOS con un módulo instalador Windows.

## Dónde guarda cada cosa

| Contenido | Ruta |
| --- | --- |
| Programa | `%LOCALAPPDATA%\Programs\Hemeroteca-Hemeroteca` |
| Base y configuración privada | `%LOCALAPPDATA%\Hemeroteca-Hemeroteca\data` |
| Errores de instalación | `%LOCALAPPDATA%\Hemeroteca-Hemeroteca\logs\instalacion.log` |
| Errores de la aplicación | `%LOCALAPPDATA%\Hemeroteca-Hemeroteca\logs\aplicacion.log` |

Cada cuenta Windows utiliza sus propios datos y configuración. Las PC de
consulta acceden a la base de la principal mediante la conexión autorizada.

## Actualizar o desinstalar

### Actualización 1.0.5: botones del catálogo y operaciones autorizadas

1. Cierra Hemeroteca e instala **Hemeroteca-Hemeroteca-Setup-1.0.5-x64.exe** en la
   principal y todas las secundarias, con la misma cuenta Windows de cada instalación.
2. Abre Hemeroteca en la principal y luego en la secundaria autorizada.
3. Entra como administrador regular y abre **Catálogo de periódicos**.
4. Verás **Registrar ejemplar**, **Consultar catálogo**, **Editar** y **Eliminar**,
   aunque estén deshabilitados por falta de permiso.
5. Solicita los permisos necesarios. Cuando el maestro los apruebe, los
   controles se actualizarán automáticamente en unos cinco segundos.
6. **Catálogo de periódicos** habilita el registro a un administrador regular.
   Para editar o eliminar se requiere el permiso de esa operación y seleccionar
   una fila. Estas operaciones funcionan también en las PC secundarias autorizadas.

La actualización conserva los datos, las cuentas, las solicitudes y las
autorizaciones de computadoras. El esquema continúa en versión 4.

### Actualización 1.0.4: tipo de cuenta y registro desde secundarias

1. Cierra Hemeroteca e instala **Hemeroteca-Hemeroteca-Setup-1.0.4-x64.exe** en la
   principal y las secundarias, usando la misma cuenta Windows de cada instalación.
2. Mantén abierta Hemeroteca en la principal.
3. En **Crear mi cuenta**, elige **Usuario regular** o **Administrador regular**.
   Completa tus datos, tres preguntas y guarda el código de recuperación.
4. Inicia sesión con la cuenta de administrador regular y solicita
   **Catálogo de periódicos** desde **Solicitudes de acceso**.
5. El maestro aprueba la solicitud desde la principal.
6. El administrador regular abre **Catálogo de periódicos → Registrar ejemplar**
   desde la principal o una secundaria autorizada. Completa todos los campos y guarda.

Las cuentas nuevas comienzan con consulta y solicitudes. La actualización
conserva las cuentas y accesos anteriores; el esquema pasa a versión 4 y la
aplicación guarda una copia SQLite antes de migrar una base existente.
Esta versión admite restaurar respaldos de esquema 3 y 4.

### Actualización 1.0.3: envío de solicitudes desde las PC secundarias

1. Cierra Hemeroteca en ambas PC e instala
   **Hemeroteca-Hemeroteca-Setup-1.0.4-x64.exe** en cada una con la misma cuenta
   Windows de la instalación anterior. Se conservan los datos y autorizaciones.
2. Mantén Hemeroteca abierta en la principal.
3. Inicia sesión en la secundaria, abre **Solicitudes de acceso** y pulsa
   **Solicitar permiso**.
4. Elige una acción disponible, escribe el motivo y pulsa **Enviar solicitud**.
5. En la principal, el maestro abre **Solicitudes de acceso → Actualizar**
   y revisa la solicitud. El usuario consulta la respuesta con **Actualizar**.

El servidor recibe y guarda las solicitudes de las PC autorizadas usando la
cuenta que inició sesión. Se conservan las reglas actuales de aprobación,
rechazo y permisos concedidos. Esta versión incluye el registro desde PC
autorizadas de 1.0.2 y la corrección de WinError 10054 de 1.0.1.

### Actualización 1.0.2: registro desde cualquier PC autorizada

1. Cierra Hemeroteca en ambas PC e instala
   **Hemeroteca-Hemeroteca-Setup-1.0.4-x64.exe** en cada una con la misma cuenta
   Windows utilizada anteriormente. Se conservan los datos y las autorizaciones.
2. Mantén Hemeroteca abierta en la principal.
3. En una PC ya autorizada, pulsa **Crear mi cuenta** en el inicio de sesión.
4. Completa nombre, documento, contraseña y tres preguntas de seguridad.
5. Guarda el código de recuperación e inicia sesión.

La cuenta se guarda en la principal como **Usuario regular** y sirve desde
cualquier PC autorizada. El maestro sigue gestionando sus permisos. Si la PC
es nueva, primero sigue la autorización de [la guía de red](RED_LOCAL.md).
Esta versión incluye la corrección de WinError 10054 de la entrega anterior.

### Actualización 1.0.1: búsqueda de computadoras

Corrige el manejo del error **WinError 10054** durante la detección de PC.
Windows puede producir ese aviso cuando se envía una búsqueda UDP a un puerto
sin una aplicación en espera. Ahora la búsqueda continúa recibiendo las
respuestas de las otras computadoras y el receptor de consulta permanece activo.

1. Cierra Hemeroteca en ambas PC.
2. Abre el instalador **1.0.4** en cada una, con la misma cuenta
   Windows utilizada para la instalación anterior. No necesitas desinstalar.
3. En la PC secundaria, abre **Preparar PC de consulta** y deja su ventana abierta.
4. En la principal, entra como maestro y pulsa **Computadoras conectadas →
   Buscar computadoras**. Autoriza el equipo con su código temporal.

La actualización conserva los datos y la configuración de Hemeroteca. Si no aparecen
equipos, consulta [las comprobaciones de red](RED_LOCAL.md#6-si-no-aparece-la-otra-computadora).
La autorización del maestro, las firmas de equipo y HTTPS se mantienen.

### Reinstalar y desinstalar

Cierra la aplicación antes de reinstalar. Instalar otra vez actualiza el
programa y conserva la base que esta versión ya tenga guardada. Haz primero
un respaldo `.hmbackup` desde la aplicación.

Para desinstalar, abre **Configuración de Windows → Aplicaciones**, elige
**Hemeroteca - Hemeroteca** y pulsa **Desinstalar**. También hay un acceso en el menú
Inicio. Se quita el programa y la tarea de respaldo que le corresponde; se
conservan tus datos, respaldos y Python, que puede ser utilizado por otros
programas.

Si reinstalas después de desinstalar, el maestro debe usar **Reintentar
programación de Windows** en **Respaldos de seguridad** para volver a crear
la tarea diaria; se conservan la clave y los archivos existentes.

## Documentación instalada

- [Manual de usuario](MANUAL_USUARIO.md).
- [Red local y autorización de computadoras](RED_LOCAL.md).
- [Respaldos y reportes PDF](RESPALDOS_Y_REPORTES.md).

El menú Inicio incluye versiones HTML de estas guías para leerlas en el navegador.
