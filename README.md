# DiscContainerController
A docker-based discord bot to control other docker containers on the host. Built with [DiscordPy](https://discordpy.readthedocs.io/en/stable/interactions/api.html).

## Config ##
You need to pass 2 different environment variables to the container to get it to function.
- DISCORD_GUILD_ID = ${DISCORD_GUILD_ID}
- DISCORD_BOT_TOKEN = ${DISCORD_BOT_TOKEN}
    - If you need information on how to create a discord bot, please see the section below on [setting up a discord bot](#setting-up-a-discord-bot)

You also need to mount the docker sock as a volume to the container to be able to control containers.
- /var/run/docker.sock:/var/run/docker.sock

You can find an example in [docker-compose-example.yml](https://github.com/thisismygithubok/DiscContainerController/blob/main/docker-compose-example.yml)

### Setting Up a Discord Bot ###
1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application
    - Name it whatever you'd like the app to be named, in this case I've used "DiscContainerController"
3. On the "General Information" page, give it a name and description.
4. On the "Installation" page, change the install link to "None"
5. On the "Bot" page, disable "Public Bot", and enable "Message Content Intent"  
6. On the "OAuth2" page, in the OAuth2 URL Generator section, choose "bot".
    - In the "Bot Permissions" section below this, in text permissions, choose "Send Messages" and "Manage Messages".
    - Copy the generated URL at the bottom and paste it into your browser. This will open the add bot to discord screen IN DISCORD. Select the server you want to add the bot to, and viola!
7. You should now have the bot available, and you can change the permissions to narrow it to a specific text channel of your liking.