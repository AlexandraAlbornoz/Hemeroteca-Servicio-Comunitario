# Conectar computadoras a Hemeroteca en Windows

Solo el **administrador maestro** autoriza o retira computadoras. Cada PC
requiere la aplicación y debe estar conectada a la misma red WiFi o cableada.
La PC principal debe permanecer encendida con Hemeroteca abierta.

## 1. Preparar cada computadora

Si utilizas el instalador Hemeroteca, abre **Hemeroteca-Hemeroteca-Setup-1.0.5-x64.exe**
en cada computadora y después el acceso **Hemeroteca - Hemeroteca**. Continúa con
el paso 2; los siguientes pasos de preparación manual son para el código fuente.

1. Copia el código, `assets`, `requirements.txt`, los archivos `.cmd` y
   los scripts `.ps1` de la raíz y `backup_worker.py`. No copies `data` ni `.venv` de otra PC.
2. Abre `Preparar_Windows.cmd` una vez y espera a que termine.
3. Abre `Iniciar_Hemeroteca.cmd` para utilizar la aplicación.

La PC principal contiene la base. Las demás consultan sus datos. Cada persona
utiliza su propio documento y contraseña después de conectar el equipo.

## 2. Activar la computadora principal

1. Registra al administrador maestro en el primer inicio y guarda su código de
   recuperación. Entra con su documento y contraseña.
2. Abre **Computadoras conectadas** en el menú lateral.
3. Escribe tu contraseña de maestro y pulsa **Activar esta PC como principal**.
4. Pulsa **Permitir la red en Windows**. Windows puede pedir autorización del
   responsable de esa computadora. Completa el permiso y vuelve a Hemeroteca.

La aplicación obtiene la dirección de red automáticamente. No necesitas escribir
IP, puerto o huellas de certificados.

## 3. Conectar otra computadora

### En la otra PC

1. Abre Hemeroteca.
2. Pulsa **Preparar PC de consulta**. Si no aparece directamente, abre
   **Más opciones y cuentas anteriores**.
3. Deja abierta la ventana. Muestra el **nombre de la PC** y un **código temporal**.
4. Si es necesario, usa **Permitir la red en Windows** en esa misma ventana.

Preparar la PC solamente la deja en espera. La aprobación se realiza en la PC
principal y requiere al maestro.

### En la PC principal

1. El maestro abre **Computadoras conectadas**.
2. Pulsa **Buscar computadoras**.
3. Busca el nombre que aparece en la ventana de la otra PC.
4. Pulsa **Conectar esta computadora**.
5. Escribe el código temporal de esa PC y tu contraseña de maestro.
6. Pulsa **Autorizar y conectar**.

La otra computadora mostrará la confirmación y el inicio de sesión. El usuario
puede pulsar **Crear mi cuenta** allí o entrar con su cuenta personal existente.
El código de conexión vence a los cinco
minutos y es distinto del código de recuperación de una cuenta.

La búsqueda encuentra aplicaciones de Hemeroteca abiertas y preparadas para
consulta. Las computadoras que no están en ese estado no aparecen.

### Registrarse desde una computadora autorizada

Con la PC principal encendida y Hemeroteca abierta, pulsa **Crear mi cuenta**
en cualquiera de las PC autorizadas. Elige **Usuario regular** o
**Administrador regular** y completa nombre, documento, contraseña
y tres preguntas. Guarda el código de recuperación que se muestra una sola vez
y después inicia sesión.

El servidor crea la cuenta con el perfil elegido y acceso inicial a consulta
y solicitudes; los permisos adicionales los concede el maestro. La cuenta
sirve en todas las PC autorizadas y el documento es único para toda la
hemeroteca. El maestro gestiona sus permisos desde la principal. Una PC nueva
debe completar primero la autorización anterior para ofrecer este registro.

### Enviar solicitudes desde una computadora secundaria

Con la principal encendida y Hemeroteca abierta, inicia sesión en una PC
autorizada y entra en **Solicitudes de acceso → Solicitar permiso**. Elige
una acción disponible, escribe su motivo y pulsa **Enviar solicitud**.

El servidor recibe y guarda la solicitud en la base central como **Pendiente**.
El maestro la revisa desde **Solicitudes de acceso** en la principal. Usa
**Actualizar** en ambas PC para ver las nuevas solicitudes o respuestas.
Los permisos ya concedidos y los que tienen una solicitud pendiente se
excluyen de las opciones, según las reglas existentes.

### Registrar ejemplares desde una secundaria

1. Crea una cuenta de **Administrador regular** o utiliza una cuenta de ese perfil.
2. Solicita **Catálogo de periódicos** y espera que el maestro lo apruebe.
3. Abre **Catálogo de periódicos → Registrar ejemplar** en la secundaria autorizada.
4. Completa los campos y pulsa **Guardar ejemplar**. Se guarda en la principal.

El servidor comprueba la sesión, el perfil y el permiso al guardar. El permiso
Catálogo permite el alta de ejemplares para un administrador regular. Los
botones Registrar ejemplar, Consultar catálogo, Editar y Eliminar se muestran
siempre en su catálogo. Se habilitan según los permisos aprobados en unos cinco
segundos; Editar y Eliminar requieren además seleccionar una fila.
Las PC autorizadas pueden editar o eliminar ejemplares con los permisos
**Editar ejemplares** y **Eliminar ejemplares**, respectivamente. Registrar
fechas sin publicación requiere **Registrar ejemplares**. Todos los cambios
se validan y guardan en la base principal. Instala Hemeroteca **1.0.5 en ambas PC**.

## 4. Retirar una computadora

En la PC principal, el maestro abre **Computadoras conectadas**, busca el equipo
en **Computadoras autorizadas** y pulsa **Retirar acceso**. Confirma su
contraseña. Se invalidan sus sesiones y se rechazan sus siguientes peticiones.
Para conectarla otra vez, debe repetirse la preparación y aprobación.

Nadie puede aprobar equipos utilizando una cuenta regular ni introduciendo una
IP por fuera del asistente. Una PC autorizada sigue necesitando una cuenta de
usuario válida para consultar datos.

## 5. Cambiar la PC principal

La nueva PC debe estar ya autorizada y conectada como cliente.

1. En esa PC, inicia sesión como maestro.
2. Abre **Computadoras conectadas** y pulsa **Convertir esta PC en la principal**.
3. Escribe tu contraseña y pulsa **Trasladar a esta PC**.
4. Mantén ambas aplicaciones abiertas hasta terminar.
5. Inicia sesión nuevamente. La PC anterior pasará a consulta; las demás
   conservarán su autorización y recibirán la dirección del nuevo servidor.
6. Revisa **Respaldos de seguridad** en la nueva PC principal y configura allí
   la carpeta, clave y tarea diaria. Esos datos locales no se transfieren con SQLite.

El traslado integrado admite bases de hasta 64 MiB. El host anterior bloquea
sus escrituras antes de exportar; la PC destino comprueba la copia antes de
activarse. La identidad del antiguo servidor se autoriza como cliente dentro
de la misma transferencia aprobada por el maestro.

Si se interrumpe, mantén las aplicaciones abiertas. En la PC anterior usa
**Más opciones y cuentas anteriores → Recuperar un traslado interrumpido** y
confirma las credenciales maestras. El destino debe seguir en espera; el sistema
cancela su activación antes de reactivar la copia anterior. Si el destino ya
está activo, continúa usando ese nuevo servidor. Ante un apagado que impida
comprobar el estado de ambos, requiere asistencia técnica; conserva los respaldos.

## 6. Si no aparece la otra computadora

- Si **Buscar computadoras** muestra **WinError 10054**, cierra Hemeroteca y
  actualiza ambas PC con el instalador Hemeroteca **1.0.4**, que incluye la corrección
  de la versión 1.0.1. Utiliza la misma cuenta
  Windows de la instalación anterior; se conservan los datos. Luego vuelve a
  abrir **Preparar PC de consulta** en la secundaria y busca desde la principal.
- Comprueba que ambas estén en la misma red y que la otra tenga abierta la
  ventana **Preparar PC de consulta**.
- Si el código venció, cierra esa ventana y vuelve a prepararla.
- Pulsa **Permitir la red en Windows** en ambos equipos.
- Windows debe tener la conexión de confianza como **Red privada**. El asistente
  lo indica si necesita ese cambio. Las redes públicas o de invitados pueden
  impedir que las computadoras se comuniquen.
- Si Windows pide permisos administrativos, debe atenderlos el responsable del
  equipo. Las políticas de una institución pueden requerir asistencia técnica.
- Si una PC fue desconectada por el maestro, debe autorizarse de nuevo.
- Utiliza una sola ventana de Hemeroteca por computadora.

## 7. Cómo se controla el acceso

La búsqueda utiliza UDP dentro de la LAN. No concede permisos y no abre archivos
SQLite de otros equipos. El código temporal autentica el intercambio de claves
y direcciones; no se envía ese código en texto en las peticiones.

Cada computadora genera una clave privada Ed25519 que conserva localmente. El
maestro registra su clave pública en `authorized_devices`. Las peticiones HTTPS
incluyen una firma del método, ruta, cuerpo, token, certificado de destino,
fecha y nonce. El servidor comprueba la autorización, firma, vigencia y ausencia
de reutilización **antes** de procesar registros, inicios de sesión o consultas.

El registro personal puede usarse antes de iniciar sesión, pero exige una
petición firmada de una computadora autorizada. La operación
`users.register_user` recibe los datos personales, las tres preguntas y el tipo
seleccionado: Usuario regular o Administrador regular. El servidor valida esos
dos perfiles, documento único, contraseña y preguntas. Las cuentas nuevas
comienzan con consulta y solicitudes. El maestro concede los permisos adicionales. Limita los
intentos de registro a diez por minuto por computadora. El código recién
generado se devuelve únicamente en la respuesta al registro; se conserva su hash.

Las sesiones de usuario están asociadas al equipo autorizado. Retirar ese
equipo invalida sus sesiones. La API no expone métodos para aprobar dispositivos;
la aprobación y revocación se realizan desde los servicios locales con rol
maestro y confirmación de su contraseña.

El envío de solicitudes requiere una PC autorizada y una sesión de usuario
vigente. El servidor obtiene al solicitante de esa sesión y calcula los
permisos disponibles sobre la base central. La lista LAN permite
`requests.available_permissions` y `requests.submit_request`. La aprobación
continúa en la principal mediante la operación local del maestro.

La interfaz utiliza las operaciones autenticadas `periodicos.save_record` y
`periodicos.delete_issue`. El servidor obtiene la identidad desde la sesión,
valida los datos y comprueba el permiso dentro de la transacción. Catálogo
permite registrar un ejemplar nuevo a un administrador regular; editar,
eliminar y registrar fechas mantienen sus permisos específicos. El cliente
conserva los permisos que devuelve el servidor para habilitar los botones.
`periodicos.register_issue` sigue disponible para compatibilidad con 1.0.4.
No se exponen por esta vía la aprobación de permisos ni la restauración de
ejemplares, que continúan reservadas al maestro en la principal.

El esquema es versión 4. Conserva `authorized_devices`, `device_nonces` y
`api_sessions.device_id`, y agrega `users.managed_permissions` para los perfiles
nuevos con permisos explícitos. Los accesos de cuentas anteriores se conservan. Los clientes de
versiones anteriores necesitan actualizarse y pasar por esta autorización.

## 8. Archivos privados

| Archivo | Uso |
| --- | --- |
| `data/hemeroteca.db` | Base de la PC principal. |
| `data/network.json` | Modo y conexión de esa PC. |
| `data/device.key` | Clave privada de la computadora; no compartir. |
| `data/tls/` | Certificado y clave TLS propios de esa PC. |
| `data/backups/` | Respaldos previos a migraciones y cambios. |

No compartas ni sincronices `data` por carpetas de red u otros servicios. Los
clientes reciben los datos a través de la aplicación. Protege la cuenta de
Windows y los respaldos: quien copie una clave privada autorizada podría
suplantar ese equipo hasta que el maestro retire su acceso.

El asistente de Windows permite solamente el ejecutable Python de este proyecto,
en la red privada y desde la subred local: TCP 8765/8767 y UDP 8766. No desactiva
el firewall. La preparación de red puede requerir permisos de administrador de
Windows, distintos del perfil maestro dentro de Hemeroteca.

## Referencias técnicas

- [Sockets de Python 3.13](https://docs.python.org/3.13/library/socket.html).
- [Firmas Ed25519 en cryptography](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/).
- [Configuración del firewall de Windows](https://learn.microsoft.com/en-us/windows/security/operating-system-security/network-security/windows-firewall/configure).
- [Avisos UDP de puerto no disponible en Windows](https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-wsasendto).
- [Control SIO_UDP_CONNRESET de Winsock](https://learn.microsoft.com/en-us/windows/win32/winsock/winsock-ioctls).

La sintaxis se revisa con Python 3.13. La detección, los permisos del firewall y
la conexión requieren comprobarse en las computadoras Windows de la red real.
