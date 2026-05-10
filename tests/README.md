# Tests

## Testing philosophy

**Two-tier approach:**

1. **Fast unit tests** (`test_parser.py`, `test_converter.py`) — use small hand-crafted XML fixtures. Run instantly, no network needed, always available. Covers edge cases and specific behaviors.

2. **Wikipedia integration tests** (`test_wikipedia.py`) — use real Wikipedia XML exports fetched via `Special:Export`. Validates the full pipeline against real-world wikitext that exercises every code path. Downloaded on first run and cached locally.

## Running tests

```bash
# Run everything (auto-downloads missing Wikipedia fixtures)
python3 -m pytest tests/

# Run in parallel (recommended — uses all CPU cores)
python3 -m pytest tests/ -n auto

# Unit tests only (no network)
python3 -m pytest tests/test_parser.py tests/test_converter.py

# Pre-download all Wikipedia fixtures
python3 tests/fetch_wikipedia_fixture.py
```

Parallel execution requires `pytest-xdist`:
```bash
apt install python3-pytest-xdist
```

Parallel runs are recommended because the integration tests call pandoc for each
fixture, and pandoc is single-threaded. With `-n auto`, each worker gets its own
pandoc process, so all CPU cores are utilised.

## Fixture files

| Directory | Purpose | Git-tracked |
|---|---|---|
| `fixtures/minimal_dump.xml` | Hand-crafted for unit tests | Yes |
| `fixtures/redirect_dump.xml` | Generated, redirect testing | Yes |
| `fixtures/with_upload.xml` | Generated, file upload testing | Yes |
| `fixtures/wikipedia_*.xml` | Real Wikipedia exports | **No** (CC BY-SA) |

Wikipedia fixtures are git-ignored because they contain Wikipedia text
licensed under CC BY-SA 3.0. They are downloaded on demand via the
`Special:Export` API and cached locally for speed.

If your team needs pre-seeded fixtures (e.g., for CI), distribute them
through a private channel or run `python3 tests/fetch_wikipedia_fixture.py`
once per checkout.

## Adding new fixtures

To add more Wikipedia pages to the integration tests, edit the
`PAGES_TO_FETCH` list in `fetch_wikipedia_fixture.py`. Choose pages
that exercise different wikitext features:

- **Math pages**: LaTeX-style formulas
- **Geography pages**: coordinates, unit conversions
- **Biographies**: infoboxes, citations
- **Technical articles**: code blocks, algorithms
- **Disambiguation pages**: lists, cross-references
- **Template namespace**: {{{param}}} syntax
- **Category namespace**: subcategory listings
- **Project namespace**: meta formatting

**Fixture size matters.** Large Wikipedia pages (200K+ XML export size)
can trigger exponential-time behaviour in pandoc's mediawiki reader — a
single page can take 20+ minutes to convert. Stick to pages below ~200K
export size. If you need to test large-page behaviour, add a dedicated
small extract instead. The pandoc invocation has a 120-second timeout
guard in `_pandoc_convert()` as a safety net.

The parametrized tests in `test_wikipedia.py` automatically pick up
any new fixtures that appear in the `fixtures/` directory.

## Future: full end-to-end testing

A live E2E test that spins up MediaWiki, creates test content, exports
a dump, imports it into Wiki.js, and verifies the result would cover the
two currently untested modules (`importer.py` and `wikijs_client.py`).
Research findings (2026-05):

### MediaWiki side — solved

MediaWiki can run entirely via PHP's built-in development server with
SQLite as the database. No Apache, no MySQL needed:

```bash
git clone https://gerrit.wikimedia.org/r/mediawiki/core.git mediawiki
composer mw-install:sqlite   # one-command bootstrap: DB + admin account
composer serve                # PHP dev server on :4000
```

Pages can be created via the MediaWiki API (bot passwords), and dumps
can be generated with `php dumpBackup.php`. Fully scriptable, ~30 seconds.

### Wiki.js side — the bottleneck

Wiki.js 2.x (current stable) has **no headless bootstrap**. The setup
wizard is a mandatory web UI step — there is no `config.yml` option, env
var, or CLI flag to create the initial admin account.

Wiki.js 3.x (alpha) adds `ADMIN_EMAIL` and `ADMIN_PASS` env vars for
headless setup, but **drops SQLite support** (PostgreSQL only) and is
not yet production-stable.

### Possible paths forward

| Approach | Database | Headless? | Risk |
|---|---|---|---|
| Wiki.js 2.x + reverse-engineer the setup wizard's GraphQL calls | SQLite | Scripted | Medium — fragile across versions |
| Wiki.js 2.x + direct DB insertion of admin user | SQLite | Scripted | Medium — schema may change |
| Wiki.js 3.x alpha | PostgreSQL | Native env vars | High — alpha software |
| Mock Wiki.js HTTP layer | None | Trivially | Low — not a true E2E |

The most promising approach is scripting the Wiki.js 2.x setup wizard:
it is a Vue.js app making GraphQL mutations that could be replicated in
Python. Once the admin account exists, the rest is standard API calls.

### When to revisit

- When Wiki.js 3.x reaches stable (headless setup + check if SQLite
  support is reconsidered).
- When the importer/client modules grow in complexity and mock-only
  coverage feels insufficient.
- When setting up a CI pipeline that warrants the infrastructure work.
