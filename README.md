# DiscContainerController
A docker-based discord bot to control other docker containers on the host. Built with [DiscordPy](https://discordpy.readthedocs.io/en/stable/).

<a href="https://hub.docker.com/r/thisismynameok/disc-container-controller"><img alt="Docker Image Size (tag)" src="https://img.shields.io/docker/image-size/thisismynameok/disc-container-controller/latest?style=for-the-badge">
<img alt="Docker Pulls" src="https://img.shields.io/docker/pulls/thisismynameok/disc-container-controller?style=for-the-badge"></a>
<img alt="GitHub commit activity" src="https://img.shields.io/github/commit-activity/m/thisismygithubok/DiscContainerController?color=brightgreen&style=for-the-badge">
<img alt="GitHub" src="https://img.shields.io/github/license/thisismygithubok/DiscContainerController?style=for-the-badge"></p>

## Slash Commands ##
This bot has several slash commands to use:
- /ping - does a simple check to see if the bot is online and responding
- /list-containers - lists the containers on the host system
- /control-container - this is an interative command:
    - First: You choose a container
    - Second: You choose an action of start, stop, or restart
    - Third: The bot will reply to you with a mention message once the action has been completed.

## Docker Run ##
```
docker run -e DISCORD_GUILD_ID=<your_guild_id> -e DISCORD_BOT_TOKEN=<your_bot_token> -e TZ=<your_tz> -v /var/run/docker.sock:/var/run/docker.sock -l section=<section_name> thisismynameok/disc-container-controller:latest
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
    - ./config:config
```

## Labels ##
You need to add container labels called 'section' to categorize and list your containers in a more friendly manner.
```
labels:
    section: "Game Servers"
```

## Settings ##
A settings.json file will be generated in your mounted config folder.
- AdminIDs - this is a discord user ID, and these IDs will have permissions to see/control all containers within all sections.
- AllowedRoles - this is a dict of role IDs and the sections those roles are allowed to see/control
- Sections - these are the sections you've defined via container labels. These are necessary to see/control containers.
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

## Setting Up a Discord Bot ##
1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
    - Name it whatever you'd like the app to be named, in this case I've used "DiscContainerController"
3. On the "General Information" page, give it a name and description.
4. On the "Installation" page, change the install link to "None"
5. On the "Bot" page, disable "Public Bot", and enable "Message Content Intent"  
    - On this same page, make sure to copy your TOKEN as you'll need to pass this to the container
6. On the "OAuth2" page, in the OAuth2 URL Generator section, choose "bot".
    - In the "Bot Permissions" section below this, in text permissions, choose "Send Messages" and "Manage Messages".
    - Copy the generated URL at the bottom and paste it into your browser. This will open the add bot to discord screen IN DISCORD. Select the server you want to add the bot to, and viola!
7. You should now have the bot available, and you can change the permissions to narrow it to a specific text channel of your liking.