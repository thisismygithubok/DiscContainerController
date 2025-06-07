import os
import asyncio
import json
import discord
import logging
import subprocess
from discord import app_commands
from discord.ext import commands
from pathlib import Path
from prettytable import PrettyTable

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class ListContainers(commands.Cog):
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

    @app_commands.command(name='list-containers', description='List all Docker containers')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore
    async def dockerlist(self, interaction: discord.Interaction):
        try:
            if not self.settings:
                await interaction.response.send_message('Error: Settings not loaded', ephemeral=True)
                return
            
            # Get allowed sections for this user
            allowed_sections = self.get_allowed_sections(interaction.user)
            if not allowed_sections and str(interaction.user.id) not in self.settings.get('AdminIDs', []):
                await interaction.response.send_message('You do not have permission to view any sections', ephemeral=True)
                return
            
            result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}'], 
                                capture_output=True, text=True, check=True)

            if result.returncode != 0:
                await interaction.response.send_message(
                    'Error encountered during docker ps -a command - see service logs.', 
                    ephemeral=True, delete_after=30
                )
                return

            containers = result.stdout.strip().splitlines()
            logger.debug(f'Found containers: {containers}')
            sections = {}

            for container in containers:
                if container:
                    inspect = subprocess.run(
                        ['docker', 'inspect', '--format', '{{.State.Status}},{{.Config.Labels.section}}', container], 
                        capture_output=True, text=True, check=True
                    )
                    status, section = inspect.stdout.strip().split(',')
                    section = section if section else "Uncategorized"
                    
                    # Only add container if user has permission for this section or is admin
                    if section in allowed_sections or str(interaction.user.id) in self.settings.get('AdminIDs', []):
                        if section not in sections:
                            sections[section] = []
                        sections[section].append([container, status.capitalize()])

            logger.debug(f'Container status: {sections}')

            if not sections:
                await interaction.response.send_message('No containers found.', ephemeral=True, delete_after=30)
            else:
                max_container_length = max(
                    len(container[0]) 
                    for section_containers in sections.values() 
                    for container in section_containers
                )
                table_width = max(max_container_length, 20)

                embeds = []
                for section, containers in sorted(sections.items()):
                    table = PrettyTable()
                    table.field_names = ['Container Name', 'Status']
                    table.max_width['Container Name'] = table_width
                    table.max_width['Status'] = 9  # fixed width for status
                    table.min_width['Container Name'] = table_width
                    table.min_width['Status'] = 6
                    table.align['Container Name'] = 'l'  # center align names
                    table.align['Status'] = 'l'  # center align status
                    table.add_rows(sorted(containers))  # sort containers within each section
                    
                    embed = discord.Embed(
                        title=f"Section: {section}",
                        description=f"```\n{table}```",
                        color=discord.Color.blue()
                    )
                    embeds.append(embed)

                # Discord allows max 10 embeds per message
                for i in range(0, len(embeds), 10):
                    chunk = embeds[i:i + 10]
                    if i == 0:
                        await interaction.response.send_message(embeds=chunk, ephemeral=True, delete_after=30)
                    else:
                        embed_list = await interaction.followup.send(embeds=chunk, ephemeral=True)
                        async def delete_after_delay():
                            await asyncio.sleep(30)
                            try:
                                if embed_list is not None:
                                    await embed_list.delete()
                            except discord.NotFound:
                                pass
                            except Exception as e:
                                logger.error(f'Error deleting message: {e}')
                        asyncio.create_task(delete_after_delay())

        except subprocess.CalledProcessError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.response.send_message(f'Error encountered in dockerlist - see service logs.', ephemeral=True, delete_after=30)

async def setup(bot):
  await bot.add_cog(ListContainers(bot))