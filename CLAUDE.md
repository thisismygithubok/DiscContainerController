# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord bot (discord.py, slash commands only, single guild) that runs in a container and controls *other* containers on the host by shelling out to the `docker` CLI over a bind-mounted `/var/run/docker.sock`. There is no Python Docker SDK and no local dev environment beyond the image.

## Commands

There is no test suite, linter, or CI. Everything is built and run via Docker.

```sh
# Build locally (native arch)
docker build -t dcc-test .

# Self-checks (the only tests; also run by `docker build`, which fails if one fails):
# docker-output parser, permission filter, settings, embed packing
python3 src/scripts/containers.py
python3 src/scripts/settings.py
cd src && PYTHONPATH=. python3 scripts/container_settings.py   # label parser, validation, settings file, dcc-env.sh
cd src && DISCORD_GUILD_ID=1 PYTHONPATH=. python3 cogs/list-containers.py   # needs discord.py; easiest inside the image

# Run the bot locally (needs a real token/guild; see "Testing" below)
docker run --rm -e DISCORD_BOT_TOKEN=... -e DISCORD_GUILD_ID=... \
  -v /var/run/docker.sock:/var/run/docker.sock -v ./config:/config dcc-test

# Check startup without connecting to a live session: a dummy token fails at login
docker run --rm -e DISCORD_BOT_TOKEN=invalid -e DISCORD_GUILD_ID=1 dcc-test

# Publish (always multi-arch; prod host is amd64, dev machine may be arm64, an agent runs on armv7)
docker buildx build --builder multi-builder --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t thisismynameok/disc-container-controller:latest --push .

# Vulnerability scan
docker scout cves --only-severity critical,high --format only-packages <image>
```

Docker Hub image name is `thisismynameok/disc-container-controller` (hyphenated). Release tags are `v`-prefixed (`v1.0.5`) on both GitHub and Docker Hub.

## Architecture

- `src/bot.py` — entry point. Validates `DISCORD_BOT_TOKEN`/`DISCORD_GUILD_ID`, then in `setup_hook` (runs once) ensures `settings.json`, loads every `cogs/*.py` as an extension, and syncs commands to the guild. `command_prefix` returns `[]` so text messages are ignored.
- `src/cogs/` — one cog per slash command (`/ping`, `/list-containers`, `/control-container`). Each command is guild-scoped with `@app_commands.guilds(...)`; there is intentionally no `copy_global_to`. Cog filenames contain hyphens, so they are only loadable as extensions, not importable normally.
- `src/scripts/containers.py` — the only place that runs docker. Async `create_subprocess_exec`; `list_containers()` returns `[(name, state, section)]` from a single `docker ps -a --format '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Label "section"}}'`, leaving out the bot's own container (matched by `HOSTNAME` = short container ID). Don't reintroduce per-container `docker inspect` (blocks the event loop and prints `<no value>` for missing labels).
- `src/agent.py` — remote agent entry point (same image, `command: python3 agent.py`). aiohttp.web server with bearer-token auth (`AGENT_TOKEN`, ≥32 chars): `GET /info` returns `{"name": <docker host's hostname>}`, `GET /containers` returns `list_containers()`, `POST /containers/{name}/{start|stop|restart}` only acts on names that `list_containers()` returns (excludes itself, blocks option-like names). It enforces no Discord permissions; the master does.
- Remote hosts on the master: `settings.json` `SecondaryHosts: [{"url", "token_env" | "token", "name"?}]` (`token_env` names an env var in the bot container; `remote_hosts` swaps in its value; an unset variable skips that host with an error naming only the variable) (v1.0.7 had a `Hosts` dict; users convert it by hand, and `check_settings_file` only warns, deliberately no rewrite. `remote_hosts` logs and skips invalid entries so one bad host never blocks the rest; only a non-list raises). `containers.resolve_hosts(hosts, local)` turns that into `{name: host}`, asking unnamed agents for `/info`; failed lookups, duplicates, names with `/` and names equal to `LocalName` are logged and skipped. `containers.list_all(named)` = local + each agent's containers named `<host>/<container>` (docker names can't contain `/`); unreachable agents are logged and skipped. `containers.control(name, action, named)` routes local vs. remote. Local containers keep bare names; their host is `LocalName` (default `primary-node`). aiohttp comes with discord.py, so there are no new dependencies.
- Settings editing (opt-in: `EnableSettingsEditing` on the master, `AGENT_ENABLE_EDIT` on agents): `src/scripts/container_settings.py` parses the `dcc.edit` label (`VAR=a,b;VAR2=c`, max 4 vars × 25 values), validates picked values against it, writes `/config/container-settings/<container>/settings.env` atomically and `docker restart`s. `src/scripts/dcc-env.sh` (copied next to it by `prepare()`, at startup for labeled containers) is the target container's entrypoint wrapper: exports the KEY=VALUE lines without eval, then execs the real entrypoint. The agent validates against its own label, never the master's request. `EditRoles` uses `allowed_sections(..., 'EditRoles')` + `permitted()`. Containers are 5-tuples `(name, state, section, image, dcc.edit)`; v1.0.8 agents send 3 (padded with `''`).
- `containers.docker()` refuses anything but `ps`/`info`/`start`/`stop`/`restart` (`DOCKER_COMMANDS`): that is what keeps the bot inside the socket-proxy allowlist in the README. Don't add a docker command without updating that allowlist and the README.
- `src/scripts/settings.py` — `/config/settings.json` lifecycle and permissions. `allowed_sections(settings, user)` returns `None` for admins (meaning *all* sections) or a set of sections from the user's roles; `containers.permitted(containers, allowed, local)` filters on that: an entry matches `"<section>"` (any host), `"<host>/<section>"` or `"<host>/*"`. Settings are re-read on every command, so edits apply without a restart.
- `/control-container` flow: host select (only if the user can see containers on 2+ hosts; local first) → paginated select (24 per page + Prev/Next) showing status → action select → (Stop asks for confirmation) → `docker start|stop|restart`. Every request and outcome is logged with the user's name and ID. Permission is re-checked in the action callback, and the docker return code is reported. UI messages auto-delete after 30s.

### Permissions model (settings.json)

- `AdminIDs`: Discord user IDs as **strings**; see/control every container, including unlabeled ones.
- `AllowedRoles`: `{ "<role id>": ["<section>" | "<host>/<section>" | "<host>/*", ...] }`.
- `LocalName`: the bot's own host name for the host menu and host-scoped entries; default `"primary-node"`.
- `Sections`: informational only; it does not filter anything (a deliberate choice).
- A container's section is its `section` label; unlabeled containers are `"Uncategorized"`.

## Container/image details that matter

- `src/entrypoint.sh` runs as root: applies `TZ`, then adds `nonroot` to whatever group owns the mounted `docker.sock` (host GIDs vary; the image's 988 default isn't relied on), then `exec su-exec nonroot`.
- The docker CLI binary is copied from the official `docker:<ver>-cli` image instead of Alpine's `docker-cli` package, because Alpine's lagged on CVE fixes. Bump that tag for CLI security fixes.
- pip is uninstalled from the runtime venv after install (removes vendored-library CVEs), so nothing can be pip-installed at runtime.
- `discord.py` is pinned in the dockerfile; bump it deliberately.

## Logging

`discord.utils.setup_logging(root=True)` gives colored output, and `bot.run(..., log_handler=None)` prevents discord.py from adding a second handler. Don't call `logging.basicConfig` at import time in any module; it duplicates every line. `VoiceClient.warn_nacl`/`warn_dave` are disabled because voice isn't used.

## Testing against Discord

Slash commands can't be invoked by the bot itself; a human has to run them in Discord. Running a second instance with the **same token** as a deployed bot makes both receive every command, and whichever responds first wins. Stop the deployed instance first, or use a separate bot application. You need your user ID in `AdminIDs` to see anything.
