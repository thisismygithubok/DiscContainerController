# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord bot (discord.py, slash commands only, single guild) that runs in a container and controls *other* containers on the host by shelling out to the `docker` CLI over a bind-mounted `/var/run/docker.sock`. There is no Python Docker SDK and no local dev environment beyond the image.

## Commands

There is no test suite, linter, or CI. Everything is built and run via Docker.

```sh
# Build locally (native arch)
docker build -t dcc-test .

# Self-checks (the only tests): docker-output parser, permission filter, settings, embed packing
python3 src/scripts/containers.py
python3 src/scripts/settings.py
cd src && DISCORD_GUILD_ID=1 PYTHONPATH=. python3 cogs/list-containers.py   # needs discord.py; easiest inside the image

# Run the bot locally (needs a real token/guild; see "Testing" below)
docker run --rm -e DISCORD_BOT_TOKEN=... -e DISCORD_GUILD_ID=... \
  -v /var/run/docker.sock:/var/run/docker.sock -v ./config:/config dcc-test

# Check startup without connecting to a live session: a dummy token fails at login
docker run --rm -e DISCORD_BOT_TOKEN=invalid -e DISCORD_GUILD_ID=1 dcc-test

# Publish (always multi-arch; prod host is amd64, dev machine may be arm64)
docker buildx build --builder multi-builder --platform linux/amd64,linux/arm64 \
  -t thisismynameok/disc-container-controller:latest --push .

# Vulnerability scan
docker scout cves --only-severity critical,high --format only-packages <image>
```

Docker Hub image name is `thisismynameok/disc-container-controller` (hyphenated). Release tags are `v`-prefixed (`v1.0.5`) on both GitHub and Docker Hub.

## Architecture

- `src/bot.py` — entry point. Validates `DISCORD_BOT_TOKEN`/`DISCORD_GUILD_ID`, then in `setup_hook` (runs once) ensures `settings.json`, loads every `cogs/*.py` as an extension, and syncs commands to the guild. `command_prefix` returns `[]` so text messages are ignored.
- `src/cogs/` — one cog per slash command (`/ping`, `/list-containers`, `/control-container`). Each command is guild-scoped with `@app_commands.guilds(...)`; there is intentionally no `copy_global_to`. Cog filenames contain hyphens, so they are only loadable as extensions, not importable normally.
- `src/scripts/containers.py` — the only place that runs docker. Async `create_subprocess_exec`; `list_containers()` returns `[(name, state, section)]` from a single `docker ps -a --format '{{.Names}}\t{{.State}}\t{{.Label "section"}}'`. Don't reintroduce per-container `docker inspect` (blocks the event loop and prints `<no value>` for missing labels).
- `src/scripts/settings.py` — `/config/settings.json` lifecycle and permissions. `allowed_sections(settings, user)` returns `None` for admins (meaning *all* sections) or a set of sections from the user's roles; `containers.permitted()` filters on that. Settings are re-read on every command, so edits apply without a restart.
- `/control-container` flow: paginated select (24 per page + Prev/Next) showing status → action select → `docker start|stop|restart`. Permission is re-checked in the action callback, and the docker return code is reported. UI messages auto-delete after 30s.

### Permissions model (settings.json)

- `AdminIDs`: Discord user IDs as **strings**; see/control every container, including unlabeled ones.
- `AllowedRoles`: `{ "<role id>": ["<section>", ...] }`.
- `Sections`: informational only; it does not filter anything (a deliberate choice).
- A container's section is its `section` label; unlabeled containers are `"Uncategorized"`.

## Container/image details that matter

- `src/entrypoint.sh` runs as root: applies `TZ`, then adds `nonroot` to whatever group owns the mounted `docker.sock` (host GIDs vary; the image's 988 default isn't relied on), then `exec su-exec nonroot`.
- The docker CLI binary is copied from the official `docker:<ver>-cli` image instead of Alpine's `docker-cli` package, because Alpine's lagged on CVE fixes. Bump that tag for CLI security fixes.
- pip is uninstalled from the runtime venv after install (removes vendored-library CVEs), so nothing can be pip-installed at runtime.
- `discord.py` is unpinned.

## Logging

`discord.utils.setup_logging(root=True)` gives colored output, and `bot.run(..., log_handler=None)` prevents discord.py from adding a second handler. Don't call `logging.basicConfig` at import time in any module; it duplicates every line. `VoiceClient.warn_nacl`/`warn_dave` are disabled because voice isn't used.

## Testing against Discord

Slash commands can't be invoked by the bot itself; a human has to run them in Discord. Running a second instance with the **same token** as a deployed bot makes both receive every command, and whichever responds first wins. Stop the deployed instance first, or use a separate bot application. You need your user ID in `AdminIDs` to see anything.
