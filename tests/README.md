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
