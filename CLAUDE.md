# CLAUDE.md

## Project overview

Embiggenator is a Python CLI tool that generates LDAP test data and Mattermost content for local development/testing. It creates users, groups, teams, channels, posts, threads, reactions, DMs, group messages, pinned posts, and custom statuses — all from a single YAML config file.

Built for the `rroemhild/docker-test-openldap` Docker image.

## Quick reference

- **Language:** Python 3.10+
- **CLI framework:** Click
- **Dependencies:** click, faker, ldap3, pyyaml (no HTTP library — uses stdlib urllib)
- **Entry point:** `embiggenator.cli:cli`
- **Package layout:** `embiggenator/` (source), `tests/` (tests), `docs/` (markdown docs), `examples/` (example config)

## Common commands

```bash
# Install in development mode
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
coverage run -m pytest && coverage report --include="embiggenator/*" --show-missing

# Run the tool
embiggenator --help
embiggenator show-config -c examples/embiggenator.yaml
```

## Architecture

### Config resolution
Options merge in priority order: **defaults < YAML config < CLI flags**. The `build_config()` function in `config.py` handles all merging. Range values (e.g., `5-20`) are parsed by `parse_range()`.

### Key modules
- `config.py` — Config dataclasses, YAML loading, merge logic. All content generation parameters live in `ContentConfig`.
- `generators/users.py` — Faker-based LDAP user generation with uid/cn uniqueness.
- `generators/groups.py` — LDAP group generation with random member assignment.
- `generators/abac.py` — ABAC attribute assignment (uniform or weighted).
- `generators/mattermost.py` — Content orchestrator: teams → channels → posts → replies → reactions → DMs → group messages → statuses. This is the largest module.
- `generators/content.py` — `PassageBank` loads bundled literary texts and serves random passages for post content.
- `output/mattermost_client.py` — Mattermost REST API client using stdlib urllib. Includes retry with backoff on 429.
- `output/ldap_writer.py` — Live LDAP operations (populate, reset, disable, update) and Mattermost user login.
- `output/ldif_writer.py` — LDIF file generation for Docker volume mounting.
- `cli.py` — Click commands. Shares options via `_common_options` and `_ldap_connection_options` decorators.

### Data flow for `run-all`
1. `build_config()` merges config
2. `generate_users()` + `generate_groups()` create LDAP entries
3. `populate_ldap()` writes entries to live LDAP server
4. `login_mattermost_users()` logs each user in via HTTP, captures session tokens
5. `generate_mattermost_content()` creates teams/channels/posts/etc via the Mattermost API

## Conventions

### Version bumping
Three files must be updated together:
- `pyproject.toml` (`version = "X.Y.Z"`)
- `embiggenator/__init__.py` (`__version__ = "X.Y.Z"`)
- `README.md` (badge: `![Version X.Y.Z]`)

### Adding new content generation features
1. Add config fields to `ContentConfig` in `config.py` (with validation in `__post_init__`)
2. Add YAML parsing in `_load_content_from_yaml()`
3. Add API method to `MattermostClient` if needed
4. Add result counter to `ContentGenerationResult` in `models_mattermost.py`
5. Add generation logic as a new step in `generate_mattermost_content()`
6. Update CLI summary output in both `content_cmd` and `run_all_cmd`
7. Update `show-config` display
8. Update `examples/embiggenator.yaml` and `docs/configuration.md`
9. Add tests

### Testing patterns
- Config tests: create temp YAML files via `tmp_path`, call `build_config()`, assert fields
- Mattermost client tests: use a real local `HTTPServer` with `_MockHandler` (see `test_mattermost_client.py`)
- Orchestrator tests: use `MagicMock(spec=MattermostClient)` and a fixture `PassageBank` with synthetic paragraphs
- LDAP tests: mock `Connection` and `Server` from ldap3

### Code style
- Type hints throughout (PEP 604 union syntax: `str | None`)
- `from __future__ import annotations` in all modules
- No external HTTP library — stdlib `urllib.request` only
- Range config values use `_min`/`_max` suffix pairs (e.g., `posts_per_channel_min`, `posts_per_channel_max`)
- Probabilities are floats 0.0–1.0, validated in `ContentConfig.__post_init__`
