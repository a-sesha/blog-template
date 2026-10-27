# blog-template

A small personal blog in a paper-and-ink style: warm off-white page, light serif headings, monospace for data, square cards with hard
shadows, graph-paper figures. No framework, no dependencies, no server: you write HTML files, run one Python script (standard
library only, Python 3.10+) and upload a folder.

The look was extracted from the project blog it grew out of. Its visual language is modelled on the research-lab posts that style
is known for (measured type sizes and colours, nothing else): no layout, text, images or logos were copied, and the fonts are free
substitutes. The tokens are at the top of `theme/style.css`, so a few edits make it your own.

## Quick start

```bash
python build.py            # writes public/ ; open public/index.html in a browser, no server needed
python build.py --check    # also verifies every link, image, script, font and #anchor in the output exists
python build.py --publish  # the version to upload: no drafts, no draft-only notes
python -m pytest tests     # the test suite (needs pytest)
```

1. Edit `site.json`: name, description, and the final address (`"url": "https://you.example"`), which switches on the Atom feed
   (`feed.xml`), `sitemap.xml` and canonical links. Leave it empty until you know the address.
2. Add a post: create `content/posts/my-post.html` (the file name is the address, lower-case with dashes) with a front-matter block
   and the HTML of the body. Copy `hello-world.html` to start; `components.html` shows every class you can use.
3. Add a page that is not a post (About, Talks): `content/pages/*.html`; it has no date and is not listed on the home page. Link it
   from `nav` in `site.json`.
4. Upload the contents of `public/` to any static host (GitHub Pages, Netlify, Cloudflare Pages, a plain web server).

## Front matter

```
---
title: Required
date: 2026-10-26             # required for posts, YYYY-MM-DD; the home page and feed are ordered by it
description: One sentence for the home page, search results and link previews.
tags: one, two
authors: A. Writer, B. Coauthor     # default: author in site.json
links: Code | https://github.com/you/repo; Paper | https://arxiv.org/abs/0000.00000
image: images/teaser.jpg     # link-preview image, a file in content/images/
toc: true                    # table of contents from the h2 headings
draft: true                  # shown with a badge locally, left out by --publish
styles: post.css             # files in the post's own folder (see below), linked after the theme
scripts: figures.js, data.js # the same, loaded at the end of the page in this order
slug: other-address          # optional; default is the file name
---
```

Reading time, the header block (Published / Authors / Reading time / Tags) and the button row are generated from this. A link in `links:` or in `nav`
may not start with `javascript:` or `data:` (your own body HTML is not filtered). A mistake in a file stops the build with a message naming the file.

## Writing the body

Plain HTML with class names; see `content/posts/components.html` (and the page it builds) for every component with its markup:

| You want | Use |
|---|---|
| a wider figure or video | `<div class="wide">` (about 1000 px) or `<div class="full">` as a direct child of the body |
| a figure on graph paper | `<figure><div class="paper"><svg ...></svg></div><figcaption>...</figcaption></figure>` |
| cards, an annotation, key numbers | `.card` / `.card.strong`, `.callout`, `.facts > .fact` |
| link cards | `.chips > a.chip` |
| tags | `.pill`, `.pill.teal`, `.pill.butter`, `.pill.sage` |
| buttons | `a.btn`, `button.btn`, a joined row with `.seg` (+ `aria-pressed`) |
| tables, code, quotes | `table.data`, `pre > code`, `blockquote > p` + `cite` |
| optional sections | `details.appendix > summary` |
| a definition on hover or tap | `<span class="term" tabindex="0" data-title="..." data-tip="...">word</span>` |
| footnotes | `<sup class="fn"><a href="#fn1" id="r1">1</a></sup>` and `<ol class="footnotes"><li id="fn1">...</li></ol>` |
| a note to yourself | `{{#draft}}...{{/draft}}` or any element with `class="draft-only"`: visible locally, removed from the page source by `--publish` |

Headings (`<h2>`, `<h3>` without attributes) get an address and a self-link automatically. Put images and video in
`content/images/` and refer to them as `../images/name.ext` from a post.

## One engine, several sites

The code, the theme and the built-in pieces are the engine; a site is just a folder with `site.json` and `content/`. Keep your
real site in its own repository and build it with this one:

```bash
python build.py --site ../my-blog              # reads ../my-blog, writes ../my-blog/public
python build.py --site ../my-blog --publish --check
```

A site can leave out `theme/` entirely. A file under the site's `theme/` replaces the engine's file of the same name
(`theme/style.css`, `theme/layout.html`, a font), and a piece in `theme/components/` or `content/snippets/` replaces a
built-in one; the order is the site's `content/snippets/`, the site's `theme/components/`, then the engine's. Building a site never
writes into the engine's folder. This folder is itself a complete example site (the default when you pass no `--site`).

## A post with its own files

For a post with media, data or custom scripts, put a folder next to its file: `content/posts/my-post.html` and
`content/posts/my-post/`. The folder is copied to `my-post/` beside the page, so relative links inside the post
(`assets/clip.mp4`, `figures.js`) work exactly as written. List the post's own stylesheets and scripts in the front matter with
`styles:` and `scripts:` (names or `name?v=2`; nothing absolute, remote or above the folder). They load after the theme, so the
post can add its own rules without touching the theme. The folder may not contain an `index.html`.

## Reusable pieces (shortcodes)

Instead of pasting markup, call a piece by name. A piece is a small HTML file with blanks; calling it fills them in, so changing
how every callout is built means editing one file.

```
{{pill "new" color=butter}}                              a call: plain arguments and key=value arguments
{{#callout title="Heads up"}} ...HTML... {{/callout}}    a call that wraps content (and may nest other calls)
{{#figure caption="Figure 1. ..."}}{{svg pipeline.svg}}{{/figure}}      inline an SVG from content/images/
\{{pill}}                                                a backslash writes the braces literally
```

Built in (`theme/components/`): `callout`, `card`, `facts` + `fact`, `chips` + `chip`, `pill`, `button`, `figure`, `image`, `video`,
`wide`, `full`, `term`, `quote`, `appendix`, `draft`, and the `svg` inliner. `components.html` shows each one live and what it takes.

- **Your own pieces:** put `NAME.html` in `content/snippets/`. It wins over a built-in of the same name. In it, `{{key}}` is the
  argument HTML-escaped, `{{{key}}}` the argument as written, `{{key|default}}` gives a default (a blank `{{key|}}` makes it
  optional; leaving out an argument with no default is an error), `{{1}}` is the first plain argument, `{{{body}}}` the wrapped content and
  `{{{root}}}` the path back to the site root (`../` in a post), so images and links work from any depth.
- **What is never expanded:** anything inside `<pre>`, `<code>`, `<script>` and `<style>`, and a value that happens to contain braces.
  A piece cannot call another piece, but the content between `{{#name}}` and `{{/name}}` can.
- **Mistakes** (unknown piece, a misspelt argument, a missing one, an unclosed block, an unmatched quote) stop the build with the
  file name and the list of what is accepted.
- Shortcodes also work in the `intro` in `site.json`. A shortcode argument cannot contain `}}`.

## Making it yours

- **Colours and type:** the variables at the top of `theme/style.css`. Text colours were chosen for contrast (secondary text is
  5.1:1 on the paper); the tests check this, so a colour change that makes text hard to read fails a test. `--muted` is for decoration
  only.
- **Page frame:** `theme/layout.html` (head, header, footer). `{{name}}` placeholders are filled by `build.py`.
- **Fonts:** see `theme/fonts/README.md`.
- **Figures:** draw them as inline SVG so text stays selectable and sharp. The conventions that make them consistent:
  square white cards with a 1 px border and an offset shadow; thin black arrows with an open head and the label beside the arrow;
  small rounded chips for tokens; one butter-yellow callout per figure; data in two or three muted colours that keep the same meaning
  everywhere on the page; no frame, no heavy axes, a faint grid, tiny grey tick labels, round markers with a black outline.
- **Not included on purpose:** dark mode, comments, analytics, a search box, tag pages. Add what you need; nothing depends on it.

## How it is built

`build.py` reads `site.json`, `content/` and `theme/`, and writes `public/`: one folder per post (`public/my-post/index.html`),
the theme, the images, and optionally the feed and sitemap. All links are relative, so the folder also works opened from disk or from
a sub-path of a host. The output folder is cleared on each build, but only if this tool made it (a marker file), so a wrong `--out`
cannot delete your own files. It also refuses an output folder that is, contains or sits inside `content/` or `theme/`. The marker file
(`.blog-template-build`) is copied with the site; it is harmless and you can leave it out when you upload.

The page is a CSS grid with a text column and two optional wider slots, so figures break out of the column without negative margins
and never cause sideways scrolling; on a phone every slot collapses to the screen. The tests build the shipped template and a set of
small sites and check, among other things: relative paths at every depth, no broken links, escaping of titles and descriptions,
drafts left out of the feed, draft notes absent from the published source, unique ids, a valid feed and sitemap, and text contrast.

## Licence

Code and theme: not chosen yet, add a `LICENSE` file before you share the repository. Fonts: SIL Open Font License 1.1 (see
`theme/fonts/README.md`).
