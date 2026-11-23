# Cómo contribuir

1. Cree un fork y una rama con un nombre descriptivo, como `feature/filtro-fecha`.
2. Prepare el entorno siguiendo el README y reproduzca el problema o caso de uso.
3. Realice un cambio acotado y agregue pruebas cuando cambie el comportamiento.
4. Ejecute `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` desde la raíz.
5. Abra un pull request con problema, solución, validación y limitaciones.

Use UTF-8, cuatro espacios y nombres descriptivos. Siga el idioma y estilo del
módulo que modifica. Evite renombrados masivos sin necesidad. Conserve los alias
públicos existentes hasta acordar una migración.

La interfaz llama a servicios; permisos y validaciones deben comprobarse en los
servicios para que también se apliquen a operaciones de red. No agregue SQL a las
vistas. Los cambios de esquema deben considerar bases existentes y probarse sobre
copias ficticias. Nunca use datos personales en pruebas ni suba secretos o bases.

Para una nueva versión, actualice `pyproject.toml`, `src/hemeroteca/__init__.py`,
`VERSION.json` y `CHANGELOG.md` en el mismo cambio. El mantenedor revisa los PR y
publica una etiqueta `vX.Y.Z`. Esta entrega no genera instaladores.

Antes de aceptar aportes, el mantenedor debe configurar en GitHub la protección
de la rama principal y exigir que pasen las comprobaciones del workflow.
Se incluye una regla importable en `.github/rulesets/main.json`; los pasos de
activación están en `docs/seguridad.md`. Antes de abrir un PR, instale el extra
`.[security]`, ejecute `.\.venv\Scripts\python.exe -m scripts.verificar_secretos` y la auditoría
`.\.venv\Scripts\python.exe -m pip_audit --strict --require-hashes -r requirements-lock.txt`. No acepte nuevos hallazgos
mediante cambios automáticos de la línea base ni excluya archivos completos.
Para cambios de código, ejecute también los controles de `docs/calidad.md`.
Revise expresamente cualquier nueva excepción `nosec` de Bandit. No reduzca los
umbrales de cobertura ni excluya módulos para hacer pasar un PR.

Para publicar el repositorio y comprobar un primer pull request protegido, siga la [guía de GitHub](docs/publicar-en-github.md).
