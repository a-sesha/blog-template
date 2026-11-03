# Changelog

Sites should pin a tag (see "Versions" in the README) and move to a newer one only after a `--publish --check` build looks right.

## v0.4.0

- Crosswords: `{{crossword file.ipuz}}` builds a playable grid from an .ipuz file, with a timer and pause, check and reveal, clear, progress kept
  in the reader's browser, and a small flourish on a clean solve. Reads one letter or digit per square; clear messages for anything else.
- Sections: `sections` in `site.json` and `section:` in front matter give extra lists on the home page, each with its own page; `posts_slug`
  names the main one; `"reading_time": false` per section; headings link to the section pages.
- Author pages: `"author_pages": true` links each author to a page of their posts (grouped by section) and adds `authors/`.
- `links:` entries left blank (`Code |`, `Code | #`) are hidden. `draft:` and `toc:` must be clearly true or false (`draft: on` is an error, not a
  published draft).
- Theme files are linked with `?v=<hash>` so caches never pair a new page with an old stylesheet.
- `--check` also verifies `srcset`, root-relative links and exact letter case; the build renders every page before it touches the output folder.
- **Breaking:** tags are gone (a `tags:` line is ignored; no Tags row). A post or page may not be called like a section, `posts_slug` or `authors`.
  `content/snippets/crossword.html` cannot override the built-in. Stricter `site.json` types. Links in `{{button}}` and `{{chip}}` are checked
  like `links:`. Symbolic links in post folders or images are refused.
- Fixes: nav styles no longer reshape a post's "On this page" box; dark figures follow the tokens; a post folder's dotfiles are not published;
  non-UTF-8 files and an unclosed `class="draft-only"` element are messages, not tracebacks or silently cut pages.

## v0.3.1

- Dark mode is opt-in (`"dark_mode": true`); posts with colours of their own stay readable by default. Nav tap-target styling scoped to the header.

## v0.3.0

- `posts_heading` and extra home-page `sections`.

## v0.2.0

- Dark mode, `footer` option (`false` for none; no font credit line), larger nav targets and cards, and the Authors row only on posts.

## v0.1.0

- First release: MIT licence, tests on Python 3.10 and 3.12, `--site`, `content/drafts/`, page folders, shortcodes.
