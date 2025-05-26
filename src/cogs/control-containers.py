import os
import asyncio
import discord
import logging
import subprocess
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class chooseActionView(discord.ui.View):
    def __init__(self, selected_container: str, *, timeout=30):
        super().__init__(timeout=timeout)
        self.selected_action = None
        self.selected_container = selected_container
        self.add_item(selectAction())

class chooseContainerView(discord.ui.View):
    def __init__(self, *, timeout=30):
        super().__init__(timeout=timeout)
        self.selected_container = None
        self.add_item(selectContainerName())

class selectAction(discord.ui.Select):
    def __init__(self):
        options=[
            discord.SelectOption(label="Start",emoji="🟢",description="Start the selected container."),
            discord.SelectOption(label="Stop",emoji="🛑",description="Stop the selected container."),
            discord.SelectOption(label="Restart",emoji="🔄",description="Restart the selected container.")
            ]
        super().__init__(placeholder="Select an option",max_values=1,min_values=1,options=options)
    
    async def callback(self, interaction: discord.Interaction):
        logger.debug('Reached callback in selectAction class')
        if not self.view or not hasattr(self.view, 'selected_container'):
            logger.error('No view or no container selected')
            await interaction.response.send_message('Error: No container selected', ephemeral=True)
            return
        
        container_name = self.view.selected_container
        if not container_name:
            logger.error('Container name is None or empty')
            await interaction.response.send_message('Error: No container selected', ephemeral=True)
            return
        
        if self.values[0] == "Start":
            self.view.selected_action = "start"
            logger.debug('Reached option "start" inside selectAction callback')
            await interaction.response.defer()
            subprocess.run(['docker', 'start', self.view.selected_container])
            await interaction.followup.send(f'{interaction.user.mention} {self.view.selected_container} has been started')

        elif self.values[0] == "Stop":
            self.view.selected_action = "stop"
            logger.debug('Reached option "stop" inside selectAction callback')
            await interaction.response.defer()
            subprocess.run(['docker', 'stop', self.view.selected_container])
            await interaction.followup.send(f'{interaction.user.mention} {self.view.selected_container} has been stopped')

        elif self.values[0] == "Restart":
            self.view.selected_action = "restart"
            logger.debug('Reached option "restart" inside selectAction callback')
            await interaction.response.defer()
            subprocess.run(['docker', 'restart', self.view.selected_container])
            await interaction.followup.send(f'{interaction.user.mention} {self.view.selected_container} has been restarted')

class selectContainerName(discord.ui.Select):
    def __init__(self):
        containers = []
        try:
            result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}'], capture_output=True, text=True, check=True)
            if result.returncode == 0:
                containers = result.stdout.strip().splitlines()
                containers.sort()
                logger.debug(f'Found containers: {containers}')
            
        except subprocess.CalledProcessError as e:
            logger.error(f'Error executing docker command: {e}')
    
        options=[
            discord.SelectOption(label=container)
            for container in containers
        ]
        super().__init__(placeholder="Select a container",max_values=1,min_values=1,options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_container = self.values[0]
        await interaction.response.defer(ephemeral=True)
        action_view = chooseActionView(selected_container)
        action_message = await interaction.followup.send(view=action_view, ephemeral=True)
        async def delete_after_delay():
            await asyncio.sleep(30)
            try:
                if action_message is not None:
                    await action_message.delete()
            except discord.NotFound:
                pass
            except Exception as e:
                logger.error(f'Error deleting message: {e}')
        asyncio.create_task(delete_after_delay())

class controlContainers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name='control-container', description='Start, Stop, or Restart the selected Docker container.')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore
    
    async def controlContainer(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=chooseContainerView(), ephemeral=True)
        await asyncio.sleep(30)
        await interaction.delete_original_response()

async def setup(bot):
  await bot.add_cog(controlContainers(bot))