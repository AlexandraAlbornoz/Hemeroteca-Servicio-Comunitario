# Hemeroteca 2.1.4 · Prioridad del desplazamiento

Se reprodujo el doble desplazamiento: la rueda de una lista o tabla llegaba también al manejador general del formulario. Las pruebas fallaban porque cambiaba la posición de la página mientras se desplazaban las opciones o filas.

La rueda sobre un selector abre su lista y mueve sus opciones sin cambiar automáticamente la selección. Dentro del menú, incluidos su barra y los extremos de la lista, el evento no pasa al formulario. Los movimientos pequeños del panel táctil se acumulan sin provocar saltos de la página.

Los contenedores de la aplicación identifican el control más cercano al cursor. Las tablas, listas y cuadros de texto mantienen su desplazamiento propio; los bloques anidados no arrastran el exterior. Sobre el fondo del formulario sigue funcionando el scroll de la página. Los campos de una sola línea sin desplazamiento vertical propio conservan el comportamiento del formulario.

Se conservaron la navegación por teclado, la edición por clic y las validaciones existentes. No cambian el esquema ni los datos de la hemeroteca.

Validación: 116 pruebas correctas, incluidos ocho casos específicos de scroll, y las comprobaciones de pantallas, edición de los tres registros, recuperación e integración.
