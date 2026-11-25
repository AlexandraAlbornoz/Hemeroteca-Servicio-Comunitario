# Actualización v2: datos y lógica

## Aplicar la actualización

1. Cierra la aplicación anterior en todas las PC.
2. Conserva el archivo de base y actualiza únicamente el código y dependencias.
3. Instala `requirements.txt` usando Python 3.13 del entorno.
4. Abre `main.py`. Antes de migrar una base existente anterior a v2 se guarda
   `data/backups/hemeroteca-pre-v2-FECHA-HORA.db` mediante la API de respaldo SQLite.
5. El esquema pasa a `PRAGMA user_version = 2`. Se conservan cuentas, hashes de
   contraseña, preguntas existentes, inventario, permisos y auditoría.
6. Las cuentas con identificador válido se normalizan. Las demás quedan con
   `document = NULL`. Usa **Registrar documento de cuenta anterior**: cuenta por
   nombre/número, contraseña anterior y documento nuevo. No se admite correo
   para iniciar sesión.
7. Al primer acceso autenticado, se completan preguntas pendientes y se emite
   el primer código si la cuenta aún no tiene uno. Guarda ese código.

Los registros antiguos incompletos no se rellenan con datos inventados. Se
pueden consultar, retirar y restaurar; para editar sus datos se deben completar
los campos obligatorios. Las preguntas ya guardadas se conservan como hechos
permanentes. Los registros nuevos eligen tres preguntas de la lista actual.

## Cambios de base de datos

La implementación ejecutable completa está en `database/schema.py`. Es
idempotente; no ejecutes instrucciones ALTER manualmente sobre una base ya migrada.

### users

Columnas añadidas o conservadas para controlar acceso:

```sql
-- Se añaden solamente si faltan.
ALTER TABLE users ADD COLUMN document TEXT;
ALTER TABLE users ADD COLUMN recovery_pending INTEGER NOT NULL DEFAULT 0;
-- password_version y must_change_password se añaden también si la base es antigua.
CREATE UNIQUE INDEX users_document_unique
ON users(document) WHERE document IS NOT NULL;
```

`identity` se conserva por compatibilidad. En cuentas actualizadas contiene el
mismo documento normalizado; los identificadores antiguos quedan almacenados
hasta que se completa la migración de esa cuenta.

### Tablas nuevas

| Tabla | Campos principales | Función |
| --- | --- | --- |
| recovery_codes | user_id PK/FK, code_hash UNIQUE, generation, created_at | Un código vigente por cuenta; solo hash. |
| recovery_code_history | code_hash PK, user_id FK, generation, created_at | Impide reutilizar un código emitido anteriormente. |
| auth_failures | identity_hash PK, failed_attempts, locked_until | Bloqueo persistente por documento y método; 5 fallos/15 minutos. |
| api_sessions | token_hash PK, user_id FK, password_version, method, recovery_generation, expires_at | Sesiones LAN de ocho horas, revocables. |
| system_settings | key PK, value | Identidad del host activo, URL, huella y estado de traslado. |

`user_security` conserva tres preguntas y tres hashes de respuestas con sal por
usuario. La antigua `master_recovery`, si existe, se migra a esa tabla.
`recovery_codes` mantiene columnas de intentos por compatibilidad del esquema;
el bloqueo efectivo actual se centraliza en `auth_failures`.

Índices adicionales: `issues_created_at`, `api_sessions_expiration`.
Disparadores `issues_required_insert` e `issues_required_update` rechazan
campos de texto vacíos o estados no admitidos al registrar o editar ejemplares.
La validación de título/tipo/calendario también se realiza en el servicio.

## Lógica de autenticación y recuperación

### Registro

1. Normalizar documento y verificar su formato y unicidad.
2. Validar nombre, contraseña de 8–15 caracteres y tres preguntas distintas de
   la lista predefinida, cada una con respuesta de de 2 a 50 caracteres.
3. En una transacción: insertar cuenta, hashes de respuestas y código aleatorio.
4. El código usa `secrets`, prefijo HMR y 30 caracteres aleatorios agrupados.
   El historial y el índice único impiden reutilizar un código previo.
5. Guardar SHA-256 del código, nunca su texto. Entregar el texto únicamente al
   formulario que termina esa operación, que exige confirmar que fue guardado.

### Acceso mediante código

1. Documento + código vigente; comprobar intentos, estado y hash.
2. Marcar `must_change_password = 1`, `recovery_pending = 1`, aumentar
   `password_version` y revocar sesiones previas.
3. Crear una sesión restringida vinculada a la generación del código. La
   autorización bloquea consultas y operaciones mientras falte el cambio.
4. Al elegir una contraseña diferente: generar el siguiente código, actualizar
   contraseña, quitar las marcas y revocar las sesiones anteriores en la misma
   transacción. El código viejo deja de funcionar.
5. Mostrar el nuevo código una vez. En LAN, entregar además una sesión nueva.

El código anterior permanece vigente hasta completar el cambio; si se abandona
la pantalla, permite reanudar la recuperación. No existe un endpoint para
volver a consultar códigos emitidos.

### Operaciones del maestro

- **Regenerar código:** comprobar contraseña maestra y versión de la cuenta;
  cambiar únicamente el hash/generación del código e invalidar sesiones de
  recuperación asociadas al anterior. La contraseña y su versión se conservan.
- **Restablecer contraseña:** comprobar contraseña maestra; asignar una temporal
  diferente, aumentar versión, revocar sesiones y generar código nuevo. El
  titular debe cambiar la temporal y recibe entonces otro código nuevo.
- **Actualizar usuario:** validar documento/nombre/perfil y versión; invalidar
  sesiones previas. El maestro conserva su perfil y no puede eliminarse.
- **Eliminar usuario:** eliminar cuenta, permisos, preguntas, códigos y sesiones;
  conservar inventario y auditoría. El historial de hashes de códigos conserva
  la prevención de reutilización con user_id nulo.

Las preguntas y respuestas se insertan una sola vez. La recuperación actual usa
el código; las preguntas no proporcionan una vía alternativa para omitirlo.
Si el maestro pierde contraseña y código, se requiere intervención técnica sobre
una copia de respaldo; no hay una contraseña universal ni un acceso oculto.

## Consultas, orden y periodos

`PeriodicoService.search_issues` usa parámetros SQL, `ORDER BY id DESC` y
`LIMIT/OFFSET`. Devuelve items, total, page, pages y page_size. Admite hasta 100
filas por página; la pantalla solicita 8.

Los periodos usan `created_at`: 24 horas, 7 días, 15 días o 30 días. Últimos 5
limita el conjunto filtrado a cinco registros. Los filtros de publicación
usan year/month/day y se combinan con título, tipo y periodo.

Las marcas nuevas de registro se guardan en UTC con zona horaria. En la
migración, las marcas antiguas sin zona se interpretan según la zona horaria
local de la PC donde se migra. Configura correctamente esa zona antes de
migrar; las marcas antiguas que no se puedan interpretar se conservan.

## Red

SQLite solo se abre en el host. Cada petición usa una conexión propia con
claves foráneas y espera de bloqueo de 10 segundos. El cliente utiliza el
adaptador de servicios y no recibe acceso SQL arbitrario.

La API admite una lista explícita de consultas, registro personal de usuarios
y administradores regulares, mantenimiento de credenciales propias, solicitudes,
alta de ejemplares para administradores regulares autorizados y control maestro del traslado.
El registro exige una PC autorizada y firmada aunque todavía no exista una
sesión de usuario. Las sesiones se resuelven por token;
no se confía en un rol o identificador de actor enviado en JSON. Los hashes de
contraseñas/respuestas se excluyen de las respuestas normales. Solo el maestro
reautenticado puede recibir una instantánea para trasladar el servidor.

El transporte compara la huella SHA-256 del certificado antes de enviar datos
HTTP. Los clientes solo aceptan HTTPS hacia direcciones locales. Configuración
por equipo en `data/network.json`; clave y certificado en `data/tls/`.

Consulta [RED_LOCAL.md](RED_LOCAL.md) para operar el servicio y trasladarlo.

### Hemeroteca 1.0.2: registro desde PC autorizadas

`UserService.register_user(name, identity, password, security_questions)` crea
únicamente usuarios regulares mediante la transacción existente. La interfaz
local y la remota usan ese mismo flujo. `users.register_user` se incluye en
la lista LAN de operaciones sin sesión de usuario, siempre después de verificar
la firma y vigencia de la autorización de la computadora. No acepta rol, actor
ni permisos. La validación y el límite de diez intentos por minuto se realizan
en el servidor.

La respuesta contiene `user_id` y el código de recuperación recién creado;
el adaptador remoto reconstruye `RegistrationResult` para conservar el flujo
de guardado del código una sola vez. El inicio de sesión posterior utiliza
documento y contraseña contra la misma base central. El registro no entrega
una sesión ni permisos adicionales. Los documentos duplicados se rechazan.

No cambia el esquema de SQLite: utiliza las tablas de cuentas, preguntas,
códigos y auditoría ya existentes. La base se mantiene en la PC principal.

### Hemeroteca 1.0.3: solicitudes desde computadoras secundarias

Se habilita `requests.submit_request` en la lista compartida de operaciones
que utilizan el cliente y el servidor. Continúa requiriendo una sesión de
usuario y una petición firmada de una PC autorizada. El servidor obtiene el
actor de su token y utiliza la transacción existente para guardar solicitud
y auditoría. Las reglas de aprobación y rechazo permanecen en el servicio
existente del maestro en la principal.

`requests.available_permissions` calcula las opciones con los permisos reales
y las solicitudes pendientes de la cuenta en el servidor. La interfaz utiliza
esa lista y habilita **Solicitar permiso** cuando contiene opciones. El envío
valida el permiso, el motivo obligatorio de hasta 1.000 caracteres y los
duplicados pendientes. No requiere cambios en el esquema de SQLite.

### Hemeroteca 1.0.4: tipo de cuenta y alta de ejemplares con Catálogo

El registro recibe `role` y acepta únicamente Usuario regular o Administrador
regular. Ambas cuentas nuevas se insertan con `managed_permissions=1`, consulta
y solicitudes. El primer maestro sigue configurándose desde la PC principal.

El esquema pasa a versión 4 y agrega `users.managed_permissions INTEGER NOT
NULL DEFAULT 0`. El valor 0 conserva los permisos implícitos de los
administradores anteriores; el valor 1 aplica la política de permisos
adicionales aprobados por el maestro. Cambiar el perfil de una cuenta activa
aplica la política nueva y conserva los permisos que tenga concedidos.

Para un alta de ejemplar, `PeriodicoService.save_record` admite el permiso de
Catálogo cuando la cuenta es un administrador regular. Las otras operaciones
mantienen su permiso correspondiente. La UI utiliza esa misma condición para
mostrar el formulario. En una secundaria se invoca `periodicos.register_issue`,
una operación autenticada que comprueba perfil y Catálogo y admite solo los
diez campos de un ejemplar nuevo. Los datos se guardan por el servicio existente
y se auditan en la principal. El permiso se vuelve a comprobar dentro de la
transacción, de modo que una revocación impide guardar desde un formulario abierto.

Los respaldos nuevos guardan el esquema 4. La lectura admite esquemas 3 y 4;
al reconstruir una copia antigua se completa `managed_permissions=0`, conservando
los accesos anteriores. El cifrado y el formato del archivo permanecen vigentes.

### Hemeroteca 1.0.5: acciones visibles y permisos de catálogo en LAN

El administrador regular ve el panel del catálogo incluso antes de recibir
permisos. Abrir ese panel solo comprueba la sesión: sus registros se consultan
únicamente cuando existe el permiso de catálogo o uno de sus permisos de
operación, como ya exige `AccessService`. El panel muestra los cuatro botones
de registro, consulta, edición y eliminación en una sección independiente del
título, que se adapta al ancho de la ventana. Los controles quedan bloqueados
cuando falta el permiso; editar y eliminar también requieren una selección.

La vigilancia de sesión existente actualiza los permisos cada cinco segundos.
El cliente conserva los permisos de operación devueltos por el servidor y
permite las rutas autenticadas `periodicos.save_record` y
`periodicos.delete_issue`. El servicio normaliza las listas JSON, valida los
campos y comprueba el permiso dentro de la misma transacción que guarda el
cambio. Se conserva la regla de Catálogo para registrar ejemplares nuevos con
perfil de administrador regular. Edición, eliminación y fechas sin publicación
requieren sus propios permisos. `periodicos.register_issue` se conserva para
clientes de la versión anterior; se recomienda actualizar ambas PC a 1.0.5.

No cambia el esquema 4 ni la aprobación de solicitudes, gestión de cuentas,
restauración de ejemplares, red autorizada o respaldos.

## Alcance de la revisión de esta entrega

Se revisa la sintaxis con Python 3.13 sin abrir ni alterar la base de uso real.
La suite existente se adapta a documentos y recuperación por códigos; sus
resultados anteriores a esta actualización no verifican las funciones nuevas.
La validación funcional, visual y del traslado en dos equipos físicos requiere
una ejecución posterior en esos equipos.

## Referencias técnicas

- [SQLite: uso sobre red](https://www.sqlite.org/useovernet.html).
- [TLS en Python 3.13](https://docs.python.org/3.13/library/ssl.html).
- [Certificados X.509 con cryptography](https://cryptography.io/en/latest/x509/tutorial/).
- [OWASP: recuperación de contraseñas](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html).
