# mediawiki2wikijs

Migrate a MediaWiki XML dump into [Wiki.js](https://js.wiki) via its API.

## Status

This tool has been used for a single production migration of a few hundred pages with uploaded files and full revision history.
It is stable for that scope, but not battle-tested across diverse MediaWiki setups.
If your wiki uses unusual templates, heavily nested parser functions, or custom extensions, expect to write template plugins and preprocess rules. The plugin system was designed for this: see [Template Plugins](#template-plugins).

## Why XML dump, not the API?

MediaWiki's API is designed for interactive browsing and editing, not bulk export.
Key limitations that pushed toward `dumpBackup.php`:

- **Revision history**: the API can list revisions, but fetching each
  one individually is slow on large wikis. The XML dump packs all
  revisions in a single file.
- **Uploaded files**: the API has no endpoint to download the original
  binary of an uploaded file. `dumpBackup.php --uploads --include-files`
  embeds them directly in the dump as base64.
- **Consistency**: the dump is a point-in-time snapshot — no risk of
  pages or files changing while you are mid-import.
- **Offline iteration**: parsing and conversion run against a local
  file, so you can iterate on template plugins and preprocess rules
  without touching a production server.

The trade-off: generating the dump requires shell access to the MediaWiki server.
If you are a wiki user without server access, the API route (with its limitations) may be your only option.

## Features

- **Full revision history** — every revision of every page is imported as a page update, preserving edit order
- **File/image import** — uploaded files are migrated with their binary content into a configurable assets folder; file links in pages are automatically rewritten to point at the correct Wiki.js asset paths
- **Configurable metadata** — original author, timestamp, and edit comment can be embedded as HTML comments in page content, or suppressed entirely
- **Template plugin system** — MediaWiki templates are converted via configurable plugins (never silently dropped)
- **Category handling** — configurable: convert to Wiki.js tags, inline text, both, or discard
- **Configurable preprocess rules** — arbitrary regex substitutions on raw wikitext before conversion (fix corrupt syntax, pre-convert broken links, etc.)
- **Path sanitization** — page titles and filenames are converted to Wiki.js-safe paths; invalid characters are replaced with underscores, and collisions are detected with clear error messages
- **Locale & visibility** — set page language code and default visibility (public/private) per import
- **Home page rename** — optionally rename one imported page to `home` so it becomes the wiki landing page
- **Dry-run mode** — validate parsing and conversion without touching the target wiki
- **Prune mode** — delete all existing pages before re-importing (useful for re-running a failed import on a clean slate)
- **Config-file driven** — single YAML config file instead of many CLI flags

## Requirements

- **Python** 3.10+
- **Pandoc** — install via your package manager (`apt install pandoc`, `brew install pandoc`, etc.)

## Installation

```bash
git clone https://github.com/gtozzi/mediawiki2wikijs.git
cd mediawiki2wikijs
pip install -r requirements.txt
```

## Quick Start

```bash
# 1. Copy and edit the config
cp config.example.yaml config.yaml
# Edit wiki_url, api_token, input_xml, locale, etc.

# 2. Dry-run first — validates parsing and conversion without importing
python mediawiki2wikijs.py -c config.yaml --dry-run

# 3. Run the real import
python mediawiki2wikijs.py -c config.yaml
```

## Generating a MediaWiki XML Dump

Use MediaWiki's `dumpBackup.php` maintenance script:

```bash
# Full dump with all revisions and uploaded files
php dumpBackup.php --full --uploads --include-files > dump.xml

# Current revisions only (much smaller)
php dumpBackup.php --current > dump.xml
```

## CLI Reference

```
mediawiki2wikijs -c config.yaml [options]
```

| Flag | Description |
|---|---|
| `-c`, `--config PATH` | Path to YAML config file (required) |
| `--dry-run` | Parse and convert only, do not import |
| `--skip-failed` | Continue importing even if some pages fail to convert or upload |
| `--prune` | Delete ALL existing pages from the wiki before importing (prompts for confirmation) |
| `-f`, `--force` | Skip confirmation prompts (currently only affects `--prune`) |
| `-v`, `--verbose` | Enable debug-level logging |
| `-q`, `--quiet` | Suppress info messages, show warnings and errors only |

## Configuration

See `config.example.yaml` for all options with comments.

### Required

| Setting | Description |
|---|---|
| `wiki_url` | Wiki.js instance URL (e.g. `https://wiki.example.com`) |
| `api_token` | Wiki.js API token (generated in Admin → API Access) |
| `input_xml` | Path to the MediaWiki XML dump file |

### Migration behavior

| Setting | Default | Description |
|---|---|---|
| `dry_run` | `false` | If true, stops after conversion without importing |
| `no_redirects` | `false` | If true, skip redirect pages entirely |
| `lowercase_paths` | `false` | Lowercase all page paths and filenames for consistent URLs |
| `locale` | `en` | Page language code — must match an installed locale in Wiki.js (e.g. `en`, `it`, `fr`). Page paths are prefixed with this locale |
| `is_private` | `true` | Default page visibility (`true` = requires login to view) |
| `home_page` | _(none)_ | Sanitized page path to rename to `home` after import, making it the wiki landing page |
| `include_metadata` | `true` | Embed revision author, timestamp, and comment as an HTML comment in page content |
| `file_upload_dir` | `import_mw` | Wiki.js assets subdirectory for uploaded files; file links in pages are rewritten to point here |
| `namespace_separator` | `/` | How to map MediaWiki `:` namespace separator to a path separator |

### Content conversion

| Setting | Default | Description |
|---|---|---|
| `category_mode` | `tag` | How to handle `[[Category:...]]` links — `tag` (Wiki.js tags only), `text` (inline wikilinks only), `both` (tags + inline), `discard` (remove entirely) |
| `template_fallback` | `error` | `error` = fail on unknown template; `codeblock` = wrap unknown template source in a fenced code block |
| `exclude_namespaces` | `[Special, MediaWiki, User, File, Template]` | Namespaces to skip entirely (no conversion, no import). Must match namespace names in the dump |
| `preprocess_rules` | _(none)_ | Ordered list of regex substitutions applied to raw wikitext before any other processing. Each rule has `pattern` and `replacement` keys |

### Preprocess rules

The `preprocess_rules` config key lets you fix wiki-specific corruptions and pre-convert patterns that pandoc's mediawiki reader cannot handle. Rules are applied in order, each against the result of the previous substitution.

Common use cases:

- **Table closer corruption** — some dumpBackup.php versions mangle `|}` to `|)`:
  ```yaml
  preprocess_rules:
    - pattern: '(?m)^\|\)\s*$'
      replacement: '|}'
    - pattern: '(?m)^\|-\)\s*$'
      replacement: '|}'
  ```

- **Fix malformed external links** — `{{http://example.com text}}` → `[text](http://example.com)`:
  ```yaml
    - pattern: '\{\{(https?://[^\s}]+)(?:\s+([^}]*))?\}\}'
      replacement: '[$2]($1)'
  ```

- **Convert inline code templates** — `{{key}}` → `` `key` ``:
  ```yaml
    - pattern: '\{\{(\w+)\}\}'
      replacement: '`$1`'
  ```

## Template Plugins

MediaWiki templates are handled by a plugin system. Built-in plugins:

- **code_block** (fallback) — wraps unknown templates in a fenced code block
- **redirect** — handles `#REDIRECT` directives

To add custom template converters, create a module in `mw2wj/template_plugins/` that extends `TemplatePlugin` and registers itself.

## Path Sanitization

Page titles and filenames are converted to Wiki.js-safe path segments:
- Characters outside `[a-zA-Z0-9_/-]` are replaced with underscores
- Consecutive underscores are collapsed
- Leading/trailing slashes are stripped
- Optional lowercasing via `lowercase_paths: true`

Filenames additionally preserve their extension (e.g. `Diagram 1.PNG` → `Diagram_1.png` with lowercasing).

**Collision detection**: if two pages or two files map to the same sanitized path, the import aborts with a clear error message identifying both originals — no silent overwrites.

**File link rewriting**: `[[File:name.png|caption]]` in wikitext is rewritten to `![caption](/file_upload_dir/name.png)` in the final markdown, pointing at the uploaded asset. Filenames in links are sanitized identically to the uploaded file so they match.

## Known Limitations

### Page history
Revision timestamps are set server-side by Wiki.js to the import time. Original timestamps are preserved in HTML comments within each revision's content (unless `include_metadata: false`). User accounts are not migrated — all edits are attributed to the API token owner.

### File history
MediaWiki XML dumps only include the **latest** version of each uploaded file, even when generated with `--uploads --include-files`. Older file revisions live in the `oldimage` database table and are not exported to XML (see [MediaWiki XML export documentation](https://www.mediawiki.org/wiki/Manual:DumpBackup.php#Dumps_of_uploaded_files) for details). Additionally, Wiki.js does not support file versioning — re-uploading to the same filename replaces the previous version. File history cannot be preserved with the current dump format and Wiki.js API capabilities.

### Template namespace
Pages in the Template namespace (ns=10) contain parser functions (`#if`, `#switch`) and triple-brace parameter syntax (`{{{param}}}`) that pandoc cannot parse. These should be excluded via `exclude_namespaces` — the example config does this by default.

### Complex templates
Infoboxes, navboxes, and other complex templates require custom plugins to convert meaningfully. The `codeblock` fallback wraps them in a fenced code block so they are never silently dropped.

### Locale
The configured `locale` must already be installed in Wiki.js (Admin → Locales). The import will fail with a foreign-key error if it is not.

## Credits

- Conversion approach inspired by [outofcontrol/mediawiki-to-gfm](https://github.com/outofcontrol/mediawiki-to-gfm) (PHP) and [sbonaime/mediawiki2wikijs](https://github.com/sbonaime/mediawiki2wikijs) (Python, MIT)
- [mwparserfromhell](https://github.com/earwig/mwparserfromhell) by Ben Kurtovic — the gold standard wikitext parser
- [Pandoc](https://pandoc.org/) — universal document converter

## License

GNU Affero General Public License v3.0 (AGPL-3.0) — see [LICENSE](LICENSE).

Copyright (C) 2026  Gabriele Tozzi <gabriele@tozzi.eu>
