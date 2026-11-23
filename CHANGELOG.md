# Cambios

## Sin publicar — organización del código fuente

- Revisado el ZIP desde extracción nueva: contenido esencial y registro en Git.
  Documentada regeneración de referencias omitidas de Git y corregido su comando HTML.

- Revisada guía de GitHub: autenticación HTTPS, permisos del revisor, clon limpio,
  recorrido completo de forks y solución de bloqueos; eliminada guía abreviada duplicada.

- Añadida guía paso a paso para publicar en GitHub, activar Actions y seguridad,
  importar reglas y comprobar la colaboración con un primer pull request.
  Enlazada desde README, contribuciones, desarrollo y seguridad; sin cambios de aplicación.

- Repetida instalación desde ZIP y entorno nuevos siguiendo solo el README:
  dependencias con hashes, inicio/cierre real, 702 pruebas y navegación correctos.
- Guía separa comprobación de Python 3.13, creación de entorno y arranque;
  desarrollo y contribuciones usan explícitamente el intérprete de .venv.
- Limpieza de pruebas drena eventos de reposo de ttk antes de destruir sus raíces;
  la repetición completa termina sin los avisos de aplicación destruida.
- Carga opcional repetida mantiene 100 ejemplares ficticios y cero cuentas.


- Catorce ramas pendientes: 13 pruebas nuevas; 702 pruebas correctas.
  Cobertura combinada 100,00 % y ramas 100,00 %.
- Libera receptor y diálogo si Tk rechaza programar o renovar sondeos.
- Probadas 13 salidas antes pendientes; retirada una condición equivalente del menú.
- Cobertura sin exclusiones ni pragmas añadidos; ocho módulos ampliados requieren 100 %.


- Callbacks y estados finales: 10 casos nuevos; 689 pruebas correctas.
  Cobertura combinada 99,86 % y ramas 99,28 %.
- Probadas acciones sin selección, validación tras cierre, progreso y GC al finalizar.
- Revalidación de modo con firma real, rollback repetido y respaldo sin tarea Windows.
- Sin nuevos defectos funcionales detectados en estos casos; producción sin cambios.
- Nueve módulos ampliados requieren 99 % combinado individual.


- Normalización, migración e interfaz: 10 casos nuevos; 679 pruebas correctas.
  Cobertura combinada 99,69 % y ramas 98,67 %.
- Valida longitud del nombre después de normalizar y capitalizar Unicode.
- Centralizada la regla en validaciones; retiradas tres comprobaciones duplicadas.
- Probados documentos ya migrados, redirección sin gestor, modal y filtros/permisos.
- Mínimo global 99 %; nueve módulos ampliados requieren 99 % individual.


- Menús, permisos y cierre: 10 casos nuevos; 669 pruebas correctas.
  Cobertura combinada 99,53 % y ramas 98,16 %.
- Selector limpia referencias, eventos y foco pendiente al destruir su menú externamente.
- Probados permisos PDF/solicitudes, sondeo cancelado y aviso posterior a restauración.
- Siete módulos ampliados requieren 98 % combinado individual.


- Respaldos, traslado e interfaz: 14 casos nuevos; 659 pruebas correctas.
  Cobertura combinada 99,41 % y ramas 97,75 %.
- Traslados validan objeto, Base64 textual y SHA-256 antes de crear temporales.
- La reconstrucción del respaldo cierra origen si falla su segunda apertura.
- Controles, auditoría, catálogo, acceso y recuperación amplían ramas probadas.
- Mínimo global de cobertura 98 %; siete módulos ampliados requieren 97 %.


- Usuarios, integridad, catálogo y sesión: 16 casos nuevos; 645 pruebas correctas.
  Cobertura combinada 99,12 % y ramas 97,18 %.
- La copia previa al formateo cierra origen si no puede abrir el destino.
- Verificados rollback por integridad y revalidaciones de permisos en pantallas.
- Retirado filtro local del catálogo sin llamadores; las consultas SQL siguen vigentes.
- Seis módulos ampliados requieren 97 % combinado individual.


- Descubrimiento, seguridad y pantallas: 19 casos nuevos; 629 pruebas correctas.
  Cobertura combinada 98,53 % y ramas 96,01 %.
- Descarta invitaciones UDP no finitas y libera sockets tras fallos de preparación.
- Estructuras inválidas de preguntas de seguridad producen ValueError antes de hash.
- Ramas de acceso, eliminados, formateo, selector horario y entradas directas ampliadas.


- Controles, componentes y transporte: 26 casos nuevos; 610 pruebas correctas.
  Cobertura combinada 98,06 % y ramas 95,19 %.
- Bytes JSON inválidos producen ErrorConexion con cierre de conexión.
- Tamaños de página inválidos se rechazan antes de crear widgets.
- Cobertura mínima individual de los tres módulos reforzada al 95 %.


- 19 de noviembre de 2026, claves/autenticación/RPC/barreras: 31 casos nuevos,
  584 pruebas correctas; cobertura global 97,06 %, ramas 93,34 %.
- Migración de documento revalida cuenta dentro de la transacción; respuestas
  RPC y redirecciones se validan antes de cambiar sesión o configuración.
- Configuración inválida produce errores controlados y el guardado fallido limpia
  temporales. Certificado vencido indica su carpeta real.
- Descarga PDF valida contenido y contador antes de escribir. Barreras y cupos HTTP
  probados ante fallos, junto con navegación, TLS y carga asíncrona local/HTTPS.


- 19 de noviembre de 2026, usuarios/permisos/emparejamiento: 45 pruebas nuevas,
  553 correctas; cobertura global 95,80 % y ramas 91,24 %.
- Estado de cuenta exige booleano; destinatarios y versiones administradas se
  validan sin aceptar booleanos o texto como identificadores.
- Receptor temporal cierra sin arrancar y libera HTTP ante fallos de descubrimiento;
  JSON demasiado anidado y pruebas HMAC Unicode se rechazan de forma controlada.
- Contrato JSON de emparejamiento explícito; nuevas regresiones de revocación,
  permisos, sesiones obsoletas, firmas, replay y TLS local.


- 19 de noviembre de 2026: 39 casos nuevos en los módulos con menor cobertura;
  508 pruebas correctas, 94,29 % combinado y 88,51 % de ramas.
- Bases de versión futura rechazadas antes de modificar tablas; restauraciones
  informan revocaciones o errores de lectura sin ejecutar cambios.
- PDF de SQLite en memoria evita un bloqueo de archivo inválido; instrucciones
  ante ReportLab ausente actualizadas al README.
- Migraciones, recuperación, PDF, auditoría, calendario y utilidades ampliados;
  suite, navegación, integración TLS y carga asíncrona local/HTTPS verificadas.


- 19 de noviembre de 2026, consultas asíncronas: 45 casos nuevos, 469 pruebas
  correctas y 90,69 % combinado global; ramas 83,63 %.
- Rechazo de tareas restaura contador de trabajos, GC y bloqueo de la interfaz;
  los fallos al programar una carga se muestran en la sección y permiten reintentar.
- Cobertura de errores, cancelación, respuestas tardías, cambio de sesión,
  navegación pospuesta y cierre. Escenarios completos local y HTTPS verificados.
- Escenario manual actualizado al contrato de paginación 5/5/1 y al directorio
  de datos aislado. CI incorpora esos escenarios y límites de los coordinadores.


- 19 de noviembre de 2026, ampliación de solicitudes y periódicos: 55 casos nuevos,
  424 pruebas correctas y 88,87 % de cobertura global combinada.
- Filtro de acción recordado conservado y validado contra el resumen de solicitudes.
- Decisiones exigen booleano, ID entero positivo, respuesta textual y versión válida;
  datos inválidos no conceden permisos ni alteran solicitudes.
- Revocaciones y errores al leer solicitudes o fichas se informan sin escapar del callback.
- CI: mínimo global de 85 %, solicitudes 95 % y periódicos 90 %, en vistas y servicios.
  Navegación e integración TLS verificadas; dependencias y formato de datos sin cambios.


- 19 de noviembre de 2026: 49 pruebas nuevas de inicio de sesión y servidor;
  suite de 369 pruebas correctas y cobertura global de 83,12 %.
- Corregidos bloqueo al cerrar servidor sin arrancar, errores de JSON demasiado
  anidado y excepción SQLite sin manejar al iniciar sesión.
- Instalación con hashes, inicio/cierre real y suite completa comprobados de nuevo
  en una copia limpia siguiendo el README.
- CI eleva el mínimo global a 80 % y añade 90 % para login y 95 % para servidor.
  No cambia dependencias ni formato de datos.


- 17 de noviembre de 2026: 46 casos adicionales de recuperación, red, usuarios,
  reportes, mantenimiento, UDP y arranque. Suite completa de 320 pruebas correctas.
- Descubrimiento UDP puede cerrarse antes de iniciar el hilo y repetir el cierre
  sin lanzar `RuntimeError`.
- CI eleva el mínimo global a 75 % e incorpora mínimos individuales para las
  pantallas y el módulo UDP ampliados. Se mantienen los límites de respaldos.

- 24 regresiones adicionales: interfaz de respaldos con controles reales y formato
  hmbackup con cifrado, cabeceras malformadas y reconstrucción SQLite.
- El escritor rechaza claves que no sean AES-256, sales inválidas y cabeceras
  demasiado grandes antes de crear un archivo que su lector no podría abrir.
- CI añade mínimos individuales de 95 % para interfaz y formato de respaldos y
  eleva el mínimo global a 65 %. Los límites anteriores se conservan.

- Ampliación de cobertura: 49 regresiones de gestión de red y respaldos; suite
  completa de 250 pruebas correctas. Comparación detallada en `docs/ampliacion-cobertura.md`.
- Corregido el respaldo diario pendiente ejecutado antes de su hora: registra el
  día cubierto para no cancelar indebidamente el respaldo del día actual.
- CI exige al menos 60 % combinado global y 95 % individual en gestor de red y
  servicio de respaldos, manteniendo el mínimo de autenticación/autorización.

- Revisión ampliada: 201 pruebas correctas; cobertura combinada de 59,76 %
  incluyendo navegación e integración, y 86,82 % en autenticación/autorización/hashing.
- RPC de traslado recupera nombres históricos y conserva los alias de la copia
  reorganizada; ejecutables Windows por ruta absoluta.
- Contraste de paleta compartida corregido y botones con teclado y foco visible.
- Regresiones para escritura atómica, respaldos alterados, cambio de archivo y
  fallo de disco simulado antes de restaurar.
- Dependencias de ejecución fijadas con hashes; instalación limpia y consistencia
  del entorno comprobadas. CI incorpora cobertura, Ruff y Bandit.
- Medición de catálogo sintético de 10.000 registros y documentación de límites
  de cobertura, accesibilidad, seguridad y activación de GitHub.

- Controles de seguridad: Dependabot, CodeQL, auditoría de dependencias y detector
  de secretos con línea base vacía y excepciones puntuales documentadas.
- Acciones fijadas por SHA, permisos mínimos y plantilla de protección de rama.
- Máximo de contraseña ampliado a 128 caracteres sin migrar hashes existentes;
  entradas excesivas rechazadas antes del cálculo de autenticación.
- Herramienta Windows para restringir la carpeta de datos a cuenta actual y SYSTEM.
- Preparación y CI actualizan pip; auditoría adicional de versiones instaladas.
- Revisión de seguridad validada con 192 pruebas correctas en Python 3.13.

- Paquete `src/hemeroteca` con imports explícitos y entrada por módulo.
- Pruebas automatizadas separadas de escenarios manuales.
- Recursos operativos Windows separados del código Python.
- Datos de desarrollo fuera del paquete y ruta configurable.
- Metadatos de instalación, documentación para contribuir y CI en Windows.
- Documentación previa conservada como historial.
- Instalación, primer inicio y 187 pruebas verificados desde copia limpia con Python 3.13.
- README aclarado para seleccionar intérprete y ejecutar sin activar el entorno.
- Distribución sin ejecutables ni herramientas de construcción de instaladores.

La versión funcional de referencia se mantiene en 2.4.0. Esta reorganización no
declara una nueva versión funcional publicada.
