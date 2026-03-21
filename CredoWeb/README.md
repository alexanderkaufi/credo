# CredoWeb

Diese Datei-Sammlung enthält zwei Ebenen:

- die webvorbereiteten Markdown-Inhalte im Ordner `CredoWeb/`
- die erzeugte statische Website im Ordner `CredoWeb/site/`

## Neu bauen

```bash
cd "CredoWeb"
python3 build_site.py
```

## Lokal ansehen

```bash
cd "CredoWeb"
python3 -m http.server --directory site 8000
```

Dann im Browser:

- `http://localhost:8000/`
