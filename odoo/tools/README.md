# Tools for releasing the Odoo modules

## Odoo Apps Store pictures (`apps_store/`)

Every released module has `static/description/` with `icon.png`, `banner.png`, `index.html` (the page of the
module in Odoo Apps) and screenshots.

- `render.py` draws `icon.png` (256×256) and `banner.png` (560×280) in the Kalamiri style from `icon.html`,
  `banner.html`, a glyph in `glyphs/` and the texts in `modules.json`. For a new module add it to `modules.json`
  (and a glyph), then `python render.py <module>`.
- `screenshots.py <spec.json>` logs in to an Odoo test database and saves screenshots of its pages. Use a test
  database and hide internal data (addresses, notes, names) with the `script` of a shot.

Both need Microsoft Edge and the Python package `websocket-client`.

## Release (`publish.py`)

Modules are developed here and released to
[odoo-croatia](https://github.com/kalamiridev/odoo-croatia) (branch `19.0`, modules at the root, as the Odoo Apps
Store expects). The release repository is never edited by hand:

```
python publish.py ../../../odoo-croatia l10n_hr_price_list l10n_hr_price_list_stock
```

It checks that each module is committed and has a README, LICENSE, icon and description page, copies it without
internal notes (`CLAUDE.md`) and caches, updates the module list in the README of the release repository and commits
there with the source commit. Push the release repository yourself after a clean install test.
