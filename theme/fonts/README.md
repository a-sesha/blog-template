# Fonts

Self-hosted Latin subsets (WOFF2) of three families, all under the **SIL Open Font License 1.1**:

| Family | Used for | Files |
|---|---|---|
| Cormorant Garamond (400, 500) | headings, pull quotes | `cormorant-garamond-latin-*.woff2` |
| Source Sans 3 (400, 600) | body text | `source-sans-3-latin-*.woff2` |
| IBM Plex Mono (400, 600) | dates, captions, buttons, diagram text | `ibm-plex-mono-latin-*.woff2` |

They came from the Fontsource packages of these families (which repackage the Google Fonts releases). The licence texts are in this
folder, as the licence requires when the fonts are redistributed:

- `OFL-Cormorant-Garamond.txt` (the Cormorant Project Authors)
- `OFL-Source-Sans-3.txt` (Adobe, Reserved Font Name "Source")
- `OFL-IBM-Plex-Mono.txt` (IBM Corp., Reserved Font Name "Plex")

They were taken from the Google Fonts repository (`ofl/cormorantgaramond`, `ofl/sourcesans3`, `ofl/ibmplexmono`). Keep them with the
font files if you copy the theme elsewhere. The page footer also names the three families and the licence.

To change the typefaces, replace the files, edit the six `@font-face` rules and the `--serif`, `--sans` and `--mono`
variables at the top of `theme/style.css`, and update the footer line in `theme/layout.html`.
