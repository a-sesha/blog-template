# Fonts

Self-hosted Latin subsets (WOFF2) of three families, all under the **SIL Open Font License 1.1**:

| Family | Used for | Files |
|---|---|---|
| Cormorant Garamond (400, 500) | headings, pull quotes | `cormorant-garamond-latin-*.woff2` |
| Source Sans 3 (400, 600) | body text | `source-sans-3-latin-*.woff2` |
| IBM Plex Mono (400, 600) | dates, captions, buttons, diagram text | `ibm-plex-mono-latin-*.woff2` |

They came from the Fontsource packages of these families (which repackage the Google Fonts releases). The OFL allows
using, embedding and redistributing them with a site or template, provided the copyright notices and licence text of each
family stay with the files. This folder does not contain those licence texts: before you publish the template or the
repository publicly, add the `OFL.txt` of each family from its upstream project (Cormorant: Christian Thalmann / Catharsis Fonts;
Source Sans 3: Adobe; IBM Plex: IBM). The page footer already names the three families and the licence, as the licence expects.

To change the typefaces, replace the files, edit the six `@font-face` rules and the `--serif`, `--sans` and `--mono`
variables at the top of `theme/style.css`, and update the footer line in `theme/layout.html`.
