# Hemeroteca 2.1.0 · Cambios y validación

Fecha: 28 de octubre de 2026.

| Área | Resultado |
| --- | --- |
| Registro | Nombre y apellido separados; letras y tildes, mínimo dos letras por palabra e iniciales en mayúscula. Cédulas nuevas V de 6–8 dígitos o E de 7–8. No se registran pasaportes. |
| Contraseñas nuevas | 8–15 caracteres, con mayúsculas, minúsculas, números y símbolos; sin espacios ni controles. Se conserva la verificación de contraseñas antiguas. |
| Recuperación | Código visible una vez al terminar el registro; confirmación de conservación y cédula autocompletada en el acceso. Recuperación por código o por tres respuestas; ambas exigen contraseña nueva y rotan el código. |
| Preguntas | Respuestas visibles al escribir; las nuevas tienen 2–50 caracteres. Normalización de mayúsculas y espacios; hashes PBKDF2 con sal individual. No se revelan respuestas almacenadas. Las respuestas antiguas siguen verificándose con su regla original. |
| Permisos | Bloqueo transaccional de permisos activos y solicitudes pendientes. Reenvío tras rechazo. Historial propio sin buscador global; consulta global solo con rol maestro o concesión explícita. Aprobar y rechazar siguen reservados al maestro. |
| Ejemplares | Edición validada; número de edición y ubicaciones numéricas. Estante, gaveta o ambos; Guardar solo se habilita al completar los campos válidos. Las fichas antiguas no se reescriben automáticamente. |
| Fechas | Calendarios desde 1970, incluidos solicitudes y auditoría. Se conservan filtros por año, mes o día. Menú adicional para fechas sin publicación con o sin observación. |
| Navegación | Listas de hasta ocho filas visibles, barra cuando hace falta y apertura por teclado. Tablas con barras automáticas; recorrido por teclado y rueda. |
| Auditoría | Fecha por calendario y acción mediante selector. Se conserva consulta autorizada y trazabilidad. |
| Formateo | Solo maestro local, contraseña y frase de confirmación más aviso final. Respaldo íntegro previo. Borra datos operativos y demás cuentas; conserva maestro y su recuperación, configuración de red, auditoría y respaldos. |
| Distribución | Nombre Hemeroteca, icono de periódico, ejecutable autónomo, instalador y desinstalador con instrucciones sencillas. No se incluyen bases, claves ni datos personales en el instalador. |

## Evidencia

- `VERIFICACION.json`: 97 pruebas de negocio y validación, pantallas, recuperación mediante formularios e integración por TLS, correctas.
- `RESULTADO_RECUPERACION_INTERFAZ.json`: registro completo desde el formulario, cédula recordada, código visible y ambas recuperaciones con rotación.
- `RESULTADO_INTEGRACION.json`: red local, paginación, conflictos de edición, PDF, recuperación remota, restauración cifrada y exclusión durante mantenimiento.
- `RESULTADO_INSTALACION.json`: instalación, ejecutable, desinstalación y conservación de archivos de usuario, correctos; identifica el instalador probado por su huella.
- `RESULTADO_MIGRACION.json`: copia de la base actual migrada al esquema 6. Se conservaron todas las filas y sus contenidos; integridad y relaciones correctas; origen sin modificar.

## Compatibilidad

Se mantienen los contratos anteriores de servicios y los protocolos de red para conservar integraciones existentes. Los cambios de validación se aplican a altas y modificaciones; no se descartan datos anteriores. Las cuentas con documentos antiguos pueden usar «Usar documento de cuenta anterior» al iniciar sesión. Los respaldos de esquemas 3, 4 y 5 siguen admitidos.

La versión anterior se conserva aparte como respaldo. La nueva aplicación referencia la ubicación de datos existente mediante una configuración externa; no cambia contraseñas, respuestas ni códigos al entregar la actualización. El primer inicio crea además una copia anterior a la migración de esquema.
