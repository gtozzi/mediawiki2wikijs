# mediawiki2wikijs

Migrate a MediaWiki XML dump into [Wiki.js](https://js.wiki) via its API.

## Features

- **Full revision history** — every revision of every page is imported as a page update, preserving edit order
- **File/image import** — uploaded files (images, etc.) are migrated with their binary content
- **Original metadata** — revision author, timestamp, and edit comment are embedded in each imported page as an HTML comment (WikiJS sets timestamps server-side, so historical dates can't be preserved natively)
- **Template plugin system** — MediaWiki templates are converted via configurable plugins (never silently dropped)
- **Category handling** — configurable: convert to WikiJS tags, inline text, both, or discard
- **Dry-run mode** — validate parsing and conversion without touching the target wiki
- **Config-file driven** — single YAML config file instead of many CLI flags

## Requirements

- **Python** 3.10+
- **Pandoc** — install via your package manager (`apt install pandoc`, `brew install pandoc`, etc.)

## Installation

```bash
git clone <this-repo-url>
cd mediawiki2wikijs
pip install -r requirements.txt
```

## Quick Start

```bash
# 1. Copy and edit the config
cp config.example.yaml config.yaml
# Edit wiki_url, api_token, input_xml paths…

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

## Configuration

See `config.example.yaml` for all options. Key settings:

| Setting | Description |
|---|---|
| `wiki_url` | WikiJS instance URL (e.g. `https://wiki.example.com`) |
| `api_token` | WikiJS API token (generated in Admin → API Access) |
| `input_xml` | Path to the MediaWiki XML dump file |
| `dry_run` | If true, stops after conversion without importing |
| `category_mode` | `tag`, `text`, `both`, or `discard` |
| `template_fallback` | `error` (fail on unknown template) or `codeblock` (wrap in code fence) |

## Template Plugins

MediaWiki templates are handled by a plugin system. Built-in plugins:

- **code_block** (fallback) — wraps unknown templates in a fenced code block
- **redirect** — handles `#REDIRECT` directives

To add custom template converters, create a module in `mw2wj/template_plugins/` that extends `TemplatePlugin` and registers itself.

## Known Limitations

### Page history
Revision timestamps are set server-side by WikiJS to the import time. Original timestamps are preserved in HTML comments within each revision's content. User accounts are not migrated — all edits are attributed to the API token owner.

### File history
MediaWiki XML dumps only include the **latest** version of each uploaded file, even when generated with `--uploads --include-files`. Older file revisions live in the `oldimage` database table and are not exported to XML (see [MediaWiki XML export documentation](https://www.mediawiki.org/wiki/Manual:DumpBackup.php#Dumps_of_uploaded_files) for details). Additionally, Wiki.js does not support file versioning — re-uploading to the same filename replaces the previous version. This means file history cannot be preserved with the current dump format and WikiJS API capabilities.

### XML export corruption (table closer)
Some versions of MediaWiki's `dumpBackup.php` corrupt `|}` (table closer) to `|)`. This causes pandoc to fail with "unexpected end of input" on affected pages. Fix with a `preprocess_rules` entry in your config:

```yaml
preprocess_rules:
  - pattern: '(?m)^\|\)\s*$'
    replacement: '|}'
```

### Complex templates
Infoboxes, navboxes, and other complex templates require custom plugins to convert meaningfully. The fallback wraps them in a fenced code block so they are never silently dropped.

## Credits

- Conversion approach inspired by [outofcontrol/mediawiki-to-gfm](https://github.com/outofcontrol/mediawiki-to-gfm) (PHP) and [sbonaime/mediawiki2wikijs](https://github.com/sbonaime/mediawiki2wikijs) (Python, MIT)
- [mwparserfromhell](https://github.com/earwig/mwparserfromhell) by Ben Kurtovic — the gold standard wikitext parser
- [Pandoc](https://pandoc.org/) — universal document converter

## License

MIT
