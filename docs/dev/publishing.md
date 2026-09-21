# Publicar y mantener la documentación

## Compilar en local

```bash
pip install -r docs/requirements.txt
sphinx-build -b html docs docs/_build/html                     # inglés
sphinx-build -b html -D language=es docs docs/_build/html_es   # español
python scripts/tests/test_docs_consistency.py                  # docs <-> código
```

## Registrar en ReadTheDocs (una sola vez, requiere cuenta con acceso al repo GitHub)

1. En https://readthedocs.org → *Import a Project* → elegir `Climate-Lead-Group/relac_tx`. Nombre sugerido: `relac-tx`. Idioma: **English**. RTD lee `.readthedocs.yaml` de la raíz.
2. Crear un **segundo** proyecto desde el mismo repositorio. Nombre sugerido: `relac-tx-es`. Idioma: **Spanish**. RTD compila con `-D language=es` automáticamente según el idioma del proyecto.
3. En el proyecto principal (`relac-tx`) → *Admin → Translations → Add* → seleccionar `relac-tx-es`. A partir de ahí el menú flotante (esquina inferior) muestra el selector `en | es` en todas las páginas y conserva la ruta al cambiar de idioma.
4. Anotar la URL resultante (`https://relac-tx.readthedocs.io/`) en la sección *Documentación* del `README.md`.

Cada `git push` a `main` reconstruye ambos proyectos.

## Al cambiar la documentación en inglés

1. Editar el `.md` en `docs/`.
2. Regenerar catálogos: `sphinx-build -b gettext docs docs/_build/gettext && sphinx-intl update -p docs/_build/gettext -d docs/locale -l es`.
3. Abrir el `.po` afectado en `docs/locale/es/LC_MESSAGES/`: las entradas cambiadas aparecen marcadas `#, fuzzy` (Sphinx las muestra en inglés hasta que se revisen). Corregir la traducción y borrar la línea `#, fuzzy`. Las entradas nuevas aparecen con `msgstr ""`.
4. Compilar ambas versiones y correr `scripts/tests/test_docs_consistency.py`.

## Reglas del repositorio que afectan a docs

- `docs/_build/`, `docs/superpowers/`, `.superpowers/` y los `.mo` están en `.gitignore`.
- El `.gitignore` ignora cualquier ruta con `temp`, `copia`, `copy`, `log`, `debug`, `backup` o `audit` en el nombre: no crear `docs/_templates/` ni archivos `changelog*`.
- `docs/dev/` no se publica (`exclude_patterns` en `docs/conf.py`).
