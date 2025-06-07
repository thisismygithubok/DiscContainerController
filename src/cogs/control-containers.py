import os
import asyncio
import discord
import logging
import json
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

class ContainerPaginationView(discord.ui.View):
    def __init__(self, containers, timeout=30):
        super().__init__(timeout=timeout)
        self.containers = containers
        self.current_page = 0
        self.items_per_page = 24
        self.total_pages = (len(containers) - 1) // self.items_per_page + 1
        
        logger.debug(f"Creating pagination view with {len(containers)} containers")
        
        # Initialize without buttons first
        self.prev_button = None
        self.next_button = None
        
        self.update_select_menu()

    def update_select_menu(self):
        self.clear_items()
        
        # Add the select menu
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current_containers = self.containers[start:end]
        select_menu = selectContainerName(current_containers)
        self.add_item(select_menu)
        
        # Add navigation buttons if needed
        if len(self.containers) > self.items_per_page:
            self.prev_button = discord.ui.Button(
                label="Previous",
                style=discord.ButtonStyle.gray,
                disabled=(self.current_page == 0),
                custom_id="prev"
            )
            self.next_button = discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.gray,
                disabled=(self.current_page >= self.total_pages - 1),
                custom_id="next"
            )
            
            # Bind callback functions
            self.prev_button.callback = self.prev_callback
            self.next_button.callback = self.next_callback
            
            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    async def prev_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

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
    def __init__(self, containers):
        options = [
            discord.SelectOption(label=container)
            for container in containers
        ]
        super().__init__(placeholder="Select a container", max_values=1, min_values=1, options=options)

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
        self.settings = self.load_settings()

    def load_settings(self):
        try:
            with open('/config/settings.json', 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f'Error loading settings: {e}')
            return None
        
    def get_allowed_sections(self, user: discord.Member):
        # Check if user is admin
        if str(user.id) in self.settings.get('AdminIDs', []):
            return self.settings.get('Sections', [])

        # Get user's roles and their allowed sections
        allowed_sections = set()
        for role in user.roles:
            role_sections = self.settings.get('AllowedRoles', {}).get(str(role.id), [])
            allowed_sections.update(role_sections)

        return list(allowed_sections)
    
    @app_commands.command(name='control-container', description='Start, Stop, or Restart the selected Docker container.')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore

    async def controlContainer(self, interaction: discord.Interaction):
        try:
            if not self.settings:
                await interaction.response.send_message('Error: Settings not loaded', ephemeral=True)
                return

            # Get allowed sections for this user
            allowed_sections = self.get_allowed_sections(interaction.user)
            if not allowed_sections and str(interaction.user.id) not in self.settings.get('AdminIDs', []):
                await interaction.response.send_message('You do not have permission to control any sections', ephemeral=True)
                return

            # Get all containers and filter by section
            result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}'], 
                                capture_output=True, text=True, check=True)
            
            if result.returncode != 0:
                await interaction.response.send_message(
                    'Error retrieving container list - see service logs.',
                    ephemeral=True
                )
                return

            containers = []
            all_containers = result.stdout.strip().splitlines()
            
            # Filter containers by section permissions
            for container in all_containers:
                if container:
                    inspect = subprocess.run(
                        ['docker', 'inspect', '--format', '{{.Config.Labels.section}}', container],
                        capture_output=True, text=True, check=True
                    )
                    section = inspect.stdout.strip()
                    section = section if section else "Uncategorized"
                    
                    # Only add container if user has permission for this section or is admin
                    if section in allowed_sections or str(interaction.user.id) in self.settings.get('AdminIDs', []):
                        containers.append(container)

            if not containers:
                await interaction.response.send_message('No containers available to control.', ephemeral=True)
                return

            containers.sort()
            logger.debug(f'Creating view with {len(containers)} filtered containers')
            view = ContainerPaginationView(containers)
            logger.debug(f'Filtered containers by permission: {containers}')

            await interaction.response.send_message(view=view, ephemeral=True)
            await asyncio.sleep(30)
            await interaction.delete_original_response()

        except subprocess.CalledProcessError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.response.send_message(
                'Error retrieving container list - see service logs.',
                ephemeral=True
            )

async def setup(bot):
  await bot.add_cog(controlContainers(bot))