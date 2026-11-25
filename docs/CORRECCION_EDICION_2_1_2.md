# Hemeroteca 2.1.2 · Edición antes de guardar

Se reprodujo un fallo de foco: al pulsar el fondo o el borde de una entrada, el cursor podía quedar en el elemento decorativo, en vez del texto. El contenido seguía en estado normal, pero el clic no permitía volver a escribir donde el usuario esperaba.

La entrada compartida ahora dirige el clic de todo su rectángulo al texto y admite Ctrl+A para reemplazar el contenido. Se aplica a nombres, apellidos, contraseñas, números de cédula y demás entradas de texto creadas con el componente común. Se conservan las máscaras de contraseña, la validación numérica y las restricciones de campos deshabilitados o de solo lectura.

La prueba de interfaz recorre los tres registros —Administrador maestro, Administrador regular y Usuario regular— antes de Continuar. Comprueba reingreso por clic, reemplazo completo y borrado con Retroceso en cada campo. También se comprobaron los formularios internos y los flujos de recuperación existentes.

Resultado: 103 pruebas correctas, edición de los tres registros correcta y sin errores de callbacks. No cambian el esquema ni los datos almacenados. Los selectores y calendarios conservan sus opciones predeterminadas; esta corrección no permite modificar preguntas de seguridad ya guardadas.
