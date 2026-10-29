# DiscContainerController
A docker-based discord bot to control other docker containers on the host. Built with [DiscordPy](https://discordpy.readthedocs.io/en/stable/).

<a href="https://hub.docker.com/r/thisismynameok/disc-container-controller"><img alt="Docker Image Size (tag)" src="https://img.shields.io/docker/image-size/thisismynameok/disc-container-controller/latest?style=for-the-badge">
<img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/thisismynameok/disc-container-controller?style=for-the-badge"></a>
<img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/thisismygithubok/DiscContainerController?color=brightgreen&style=for-the-badge">
<img alt="GitHub" src="https://img.shields.io/github/license/thisismygithubok/DiscContainerController?style=for-the-badge"></p>

## Slash Commands ##
This bot has several slash commands to use. You only see the containers your [settings](#settings) allow, and the bot's own container is never listed (so it can't stop itself). The bot's menus and lists are only visible to you and delete themselves after 30 seconds.
- /ping - does a simple check to see if the bot is online and responding
- /list-containers - lists the containers you can see, grouped by section, with their status
- /control-container - this is an interactive command:
    - First: You choose a container (24 per page, with Previous/Next buttons if there are more)
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
You need to mount the docker sock as a volume to the container to be able to control containers. You also need to mount a config directory for the setting.json to be generated into
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
- AllowedRoles - a dict of role IDs and the sections those roles are allowed to see/control. A user with several roles gets the sections of all of them. Users with no admin ID and no allowed role see nothing.
- Sections - a reference list of the sections you've defined via container labels. It is informational only; access is controlled by AdminIDs and AllowedRoles.
- Example:
```
{
    "AdminIDs": [
        "1234567890101010"
    ],
    "AllowedRoles": {
        "0101010987654321": [
            "Game Servers"
        ]
    },
    "Sections": [
        "Backend",
        "Frontend",
        "Game Servers"
    ]
}
```

## Logging ##
The bot logs to the container output (`docker logs DiscContainerController`). Every container action is logged with the Discord username and user ID, for example:
```
steven (123456789012345678) requested restart on plex
plex successfully restarted
```
Failed actions, cancelled stops, and denied requests (no permission) are logged too.

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