# Hemeroteca 2.1.3 · Recuperación del foco con el mouse

Caso informado: el campo permite editar al llegar mediante Tab, pero no recupera correctamente el teclado al volver con el mouse. La revisión anterior cubría el fondo del campo y dependía del comportamiento predeterminado de Tkinter para el texto interno.

La entrada compartida ahora activa explícitamente el foco de teclado al presionar y soltar sobre el texto, y al pulsar el fondo. Los eventos del texto mantienen los bindings nativos para selección, posición del cursor, arrastre y borrado. La activación solo responde al clic; no utiliza un temporizador que pueda llevar el foco a otro campo.

Se comprobaron 108 pruebas: clic en texto y borde, regreso repetido al campo, Retroceso, Suprimir, edición intermedia, contraseña visible y oculta, tres perfiles y consultas en segundo plano. También pasaron interfaz, recuperación e integración.

No se modifican contraseñas guardadas ni el esquema. La comprobación del caso informado debe confirmarse en la pantalla del usuario después de actualizar el ejecutable.
