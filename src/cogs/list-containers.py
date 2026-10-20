import os
import asyncio
import discord
import logging
from discord import app_commands
from discord.ext import commands
from prettytable import PrettyTable
from scripts.settings import load_settings, allowed_sections
from scripts.containers import list_containers, permitted

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class ListContainers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='list-containers', description='List all Docker containers')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore
    async def dockerlist(self, interaction: discord.Interaction):
        try:
            settings = load_settings()
            if not settings:
                await interaction.response.send_message('Error: Settings not loaded', ephemeral=True)
                return
            
            # Get allowed sections for this user (None = admin)
            allowed = allowed_sections(settings, interaction.user)
            if allowed is not None and not allowed:
                await interaction.response.send_message('You do not have permission to view any sections', ephemeral=True)
                return

            sections = {}
            for container, status, section in permitted(await list_containers(), allowed):
                sections.setdefault(section, []).append([container, status.capitalize()])

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

        except RuntimeError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.response.send_message(f'Error encountered in dockerlist - see service logs.', ephemeral=True, delete_after=30)

async def setup(bot):
  await bot.add_cog(ListContainers(bot))