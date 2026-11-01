# DiscContainerController
A docker-based discord bot to control other docker containers on the host, and optionally on other hosts via a lightweight [agent](#remote-hosts). Built with [DiscordPy](https://discordpy.readthedocs.io/en/stable/).

Images are published for `linux/amd64`, `linux/arm64` and `linux/arm/v7` (e.g. Raspberry Pi / PiKVM).

<a href="https://hub.docker.com/r/thisismynameok/disc-container-controller"><img alt="Docker Image Size (tag)" src="https://img.shields.io/docker/image-size/thisismynameok/disc-container-controller/latest?style=for-the-badge">
<img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/thisismynameok/disc-container-controller?style=for-the-badge"></a>
<img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/thisismygithubok/DiscContainerController?color=brightgreen&style=for-the-badge">
<img alt="GitHub" src="https://img.shields.io/github/license/thisismygithubok/DiscContainerController?style=for-the-badge"></p>

## Slash Commands ##
This bot has several slash commands to use. You only see the containers your [settings](#settings) allow, and the bot's own container is never listed (so it can't stop itself). The bot's menus and lists are only visible to you and delete themselves after 30 seconds.
- /ping - does a simple check to see if the bot is online and responding
- /list-containers - lists the containers you can see, grouped by section, with their status
- Containers on [remote hosts](#remote-hosts) are shown as `<host name>/<container name>`
- /control-container - this is an interactive command:
    - First: If you can see containers on more than one host, you choose the host (shown with how many containers you can see on it). Otherwise this step is skipped.
    - Then: You choose a container (24 per page, with Previous/Next buttons if there are more)
    - Second: You choose an action of start, stop, or restart
    - Stop asks you to confirm first
    - Third: The bot posts a message mentioning you once the action has completed, or if it failed

## Docker Run ##
```
docker run -e DISCORD_GUILD_ID=<your_guild_id> -e DISCORD_BOT_TOKEN=<your_bot_token> -e TZ=<your_tz> -v /var/run/docker.sock:/var/run/docker.sock -v ./config:/config -l section=<section_name> thisismynameok/disc-container-controller:latest
```

## Docker Compose ##
You can find an example in [docker-compose-example.yml](https://github.com/thisismygithubok/DiscContainerController/blob/main/docker-compose-example.yml)

## Environment Variables ##
- REQUIRED
    - DISCORD_GUILD_ID
        - This is your discord server ID
    - DISCORD_BOT_TOKEN
        - This is your discord bot token
        - If you need information on how to create a discord bot, please see the section below on [setting up a discord bot](#setting-up-a-discord-bot)

- OPTIONAL
    - TZ
        - This is optional, but you can specify this for the container/logging output timezone
        - Must use IANA standard timezones

```
environment:
    DISCORD_BOT_TOKEN: ${DISCORD_BOT_TOKEN}
    DISCORD_GUILD_ID: ${DISCORD_GUILD_ID}
    TZ: ${TZ}
```

## Volumes ##
You need to mount the docker sock as a volume to the container to be able to control containers (or use a [socket proxy](#docker-socket-proxy-optional) instead). You also need to mount a config directory for the setting.json to be generated into
```
volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ./config:/config
```

## Labels ##
You need to add container labels called 'section' to categorize and list your containers in a more friendly manner. Containers without a section label are listed as "Uncategorized" (visible to admins only, unless a role is allowed "Uncategorized").

Note: the bot recognizes its own container by its hostname (Docker sets it to the container ID). If you set a custom `hostname:` for the bot's container, it will show up in its own list again.
```
labels:
    section: "Game Servers"
```

## Settings ##
A settings.json file will be generated in your mounted config folder. It is re-read on every command, so changes apply without restarting the bot.
- AdminIDs - a list of discord user IDs; these users can see/control all containers in all sections, including "Uncategorized". IDs can be written as strings or numbers.
- AllowedRoles - a dict of role IDs and what those roles are allowed to see/control. A user with several roles gets everything all of them allow. Users with no admin ID and no allowed role see nothing. Each entry is one of:
    - `"<section>"` - that section on every host (e.g. `"Game Servers"`)
    - `"<host>/<section>"` - that section on one host only (e.g. `"pikvm/Backend"`, `"primary-node/Game Servers"`)
    - `"<host>/*"` - every container on that host, including "Uncategorized" (e.g. `"pikvm/*"`)
- Sections - a reference list of the sections you've defined via container labels. It is informational only; access is controlled by AdminIDs and AllowedRoles.
- LocalName - the name of the bot's own host, shown in the host menu and used in `"<host>/..."` permissions. Defaults to `"primary-node"`.
- SecondaryHosts - remote agents on other servers (see [Remote Hosts](#remote-hosts)). Leave it as `[]` to only control the local host.
- Example:
```
{
    "AdminIDs": [
        "1234567890101010"
    ],
    "AllowedRoles": {
        "0101010987654321": [
            "Game Servers"
        ],
        "1111111111111111": [
            "pikvm/*",
            "primary-node/Backend"
        ]
    },
    "Sections": [
        "Backend",
        "Frontend",
        "Game Servers"
    ],
    "LocalName": "primary-node",
    "SecondaryHosts": [
        {
            "url": "http://100.64.0.2:8080",
            "token_env": "SERVER2_AGENT_TOKEN"
        }
    ]
}
```

## Remote Hosts ##
To control containers on other servers, run the same image as an agent on each one, then add it to `SecondaryHosts` in settings.json. The agent's containers then appear in the bot as `<host name>/<container name>`. Section labels work the same as for local containers, and permissions can also be limited to a host (see [Settings](#settings)). If an agent can't be reached, its containers are left out and a warning is logged.

```
services:
  DiscContainerController-Agent:
    image: thisismynameok/disc-container-controller:latest
    container_name: DiscContainerController-Agent
    command: ["python3", "agent.py"]
    restart: always
    environment:
      AGENT_TOKEN: ${AGENT_TOKEN}   # at least 32 characters, e.g. `openssl rand -hex 32`
      TZ: ${TZ}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "100.64.0.2:8080:8080"     # bind to a private (VPN) address, not 0.0.0.0
```
- AGENT_TOKEN (required) - shared secret; the master needs the same value (see setup step 3).
- AGENT_PORT (optional, default 8080) - port the agent listens on inside the container.
- TZ (optional) - set it to the same value as the master so both logs use the same time.

Setup:
1. Generate a token: `openssl rand -hex 32`
2. Start the agent on the remote server with that token (compose above).
3. Give the master the token as an environment variable (recommended, so it isn't stored in settings.json), e.g. in the master's compose file and `.env`:
```
environment:
    SERVER2_AGENT_TOKEN: ${SERVER2_AGENT_TOKEN}
```
   Then add the host to the master's settings.json. Settings changes apply without a restart, but a new environment variable needs `docker compose up -d`. `name` is optional; without it the host is named after the remote server's hostname:
```
"SecondaryHosts": [
    {
        "url": "http://100.64.0.2:8080",
        "token_env": "SERVER2_AGENT_TOKEN",
        "name": "server2"
    }
]
```
   `"token": "<the agent's AGENT_TOKEN>"` in place of `token_env` also works, but then the token is stored in plain text in settings.json.

   The token is never logged or shown in Discord. Anyone with Docker access on the master's host can still read it (`docker inspect` shows environment variables), as can anyone who can read the `.env` file, so keep `.env` private (`chmod 600 .env`).
4. Run `/list-containers` - the remote containers appear as `server2/<container name>`.

Host names must be unique, can't contain `/`, and can't be the same as `LocalName`. A host entry that breaks these rules, is missing `url`/`token_env`, or whose `token_env` variable isn't set, is skipped and an error is logged; the other hosts keep working. Upgrading from v1.0.7: `"Hosts": {"server2": {...}}` is now a list called `SecondaryHosts`, so `"SecondaryHosts": [{"name": "server2", ...}]`. The bot logs a warning at startup while settings.json still has `"Hosts"`.

The agent can only list, start, stop and restart containers on its host, and it never lists or controls itself. Everyone with the token has that power, and the token is sent in plain HTTP. **Only expose the agent on a private network (Tailscale, WireGuard, LAN) or behind a TLS reverse proxy (then use an `https://` url) - never directly on the internet.**

## Docker Socket Proxy (optional) ##
Mounting `docker.sock` gives a container full control of Docker, which is the same as root on the host. Instead, you can run a socket proxy that only lets through the few Docker API calls this bot uses. If the bot or agent were ever compromised, it could then only list, start, stop and restart containers, not create containers, exec into them, or read their settings (e.g. other services' passwords in environment variables).

We suggest [wollomatic/socket-proxy](https://github.com/wollomatic/socket-proxy), which can allow exactly these calls. (tecnativa/docker-socket-proxy can't: allowing start/stop there also allows creating containers.) No bot settings change - remove the `docker.sock` mount and set `DOCKER_HOST`. This works the same for the bot and for an [agent](#remote-hosts):
```
services:
  dcc-socket-proxy:
    image: wollomatic/socket-proxy:1.13.2
    container_name: dcc-socket-proxy
    restart: always
    group_add:
      - "988"    # GID that owns the host's docker.sock: `stat -c %g /var/run/docker.sock`
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    command:
      - -listenip=0.0.0.0
      - -allowfrom=DiscContainerController    # only this container may connect
      - -allowGET=/v1\.[0-9]+/(_ping|version|info|containers/json)|/_ping
      - -allowHEAD=/_ping|/v1\.[0-9]+/_ping
      - -allowPOST=/v1\.[0-9]+/containers/[a-zA-Z0-9][a-zA-Z0-9_.-]*/(start|stop|restart)
    networks: [dcc-proxy]
    # no ports: - the proxy must only be reachable on the internal network

  DiscContainerController:
    # ...as above, but without the docker.sock volume, plus:
    environment:
      DOCKER_HOST: tcp://dcc-socket-proxy:2375
    networks: [dcc-proxy, default]    # default: needed to reach Discord (and agents)
    depends_on: [dcc-socket-proxy]

networks:
  dcc-proxy:
    internal: true
```
- For an agent, use `-allowfrom=DiscContainerController-Agent`. The agent's own port stays on the default network as before.
- Blocked calls are logged by the proxy (`docker logs dcc-socket-proxy`) and show up in the bot as a failed action.
- The proxy does not know about Discord permissions: the bot can still start, stop or restart any container on that host (permissions are enforced by the bot). The proxy itself still has full access to Docker, so never publish its port.

## Logging ##
The bot logs to the container output (`docker logs DiscContainerController`). Every container action is logged with the Discord username and user ID, for example:
```
steven (123456789012345678) requested restart on plex
plex successfully restarted
```
Failed actions, cancelled stops, and denied requests (no permission) are logged too.

Agents log every action they run with the master's IP, and every request with a missing or wrong token:
```
192.168.2.3 requested restart on beszel-agent
beszel-agent restart succeeded
Rejected unauthorized GET /containers from 192.168.2.94
```

If the bot can't start (for example DISCORD_GUILD_ID isn't a number, or the config folder isn't writable), it exits with an error in the logs instead of running without commands.

## Setting Up a Discord Bot ##
1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
    - Name it whatever you'd like the app to be named, in this case I've used "DiscContainerController"
3. On the "General Information" page, give it a name and description.
4. On the "Installation" page, change the install link to "None"
5. On the "Bot" page, disable "Public Bot". No privileged intents are needed.  
    - On this same page, make sure to copy your TOKEN as you'll need to pass this to the container
6. On the "OAuth2" page, in the OAuth2 URL Generator section, choose "bot".
    - In the "Bot Permissions" section below this, in text permissions, choose "Send Messages" and "Manage Messages".
    - Copy the generated URL at the bottom and paste it into your browser. This will open the add bot to discord screen IN DISCORD. Select the server you want to add the bot to, and viola!
7. You should now have the bot available, and you can change the permissions to narrow it to a specific text channel of your liking.