import os
import asyncio
import discord
import logging
from discord import app_commands
from discord.ext import commands
from scripts.settings import load_settings, allowed_sections
from scripts.containers import docker, list_containers, permitted

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class chooseActionView(discord.ui.View):
    def __init__(self, selected_container: str, *, timeout=30):
        super().__init__(timeout=timeout)
        self.selected_container = selected_container
        self.add_item(selectAction())

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
        
        action = self.values[0].lower()
        logger.debug(f'Reached option "{action}" inside selectAction callback')
        await interaction.response.defer()

        # Re-check permission at action time: settings may have changed since the menu was shown.
        try:
            containers = await list_containers()
        except RuntimeError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.followup.send('Error retrieving container list - see service logs.', ephemeral=True)
            return
        settings = load_settings()
        allowed = allowed_sections(settings, interaction.user) if settings else set()
        if container_name not in [c[0] for c in permitted(containers, allowed)]:
            await interaction.followup.send(f'You do not have permission to control {container_name}', ephemeral=True)
            return

        code, _, err = await docker(action, container_name)
        if code != 0:
            logger.error(f'docker {action} {container_name} failed: {err.strip()}')
            await interaction.followup.send(f'{interaction.user.mention} failed to {action} {container_name} - see service logs.')
            return
        past = {'start': 'started', 'stop': 'stopped', 'restart': 'restarted'}[action]
        await interaction.followup.send(f'{interaction.user.mention} {container_name} has been {past}')

class selectContainerName(discord.ui.Select):
    def __init__(self, containers):
        options = [
            discord.SelectOption(label=name, description=state.capitalize(), emoji="🟢" if state == "running" else "🛑")
            for name, state, _ in containers
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

    @app_commands.command(name='control-container', description='Start, Stop, or Restart the selected Docker container.')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore

    async def controlContainer(self, interaction: discord.Interaction):
        try:
            settings = load_settings()
            if not settings:
                await interaction.response.send_message('Error: Settings not loaded', ephemeral=True)
                return

            # Get allowed sections for this user (None = admin)
            allowed = allowed_sections(settings, interaction.user)
            if allowed is not None and not allowed:
                await interaction.response.send_message('You do not have permission to control any sections', ephemeral=True)
                return

            containers = permitted(await list_containers(), allowed)

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

        except RuntimeError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.response.send_message(
                'Error retrieving container list - see service logs.',
                ephemeral=True
            )

async def setup(bot):
  await bot.add_cog(controlContainers(bot))