import os
import discord
import logging
import subprocess
from discord import app_commands
from discord.ext import commands
from prettytable import PrettyTable

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class ListContainers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='list-containers', description='List all Docker containers')
    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore
    async def dockerlist(self, interaction: discord.Interaction):
        try:
            result = subprocess.run(['docker', 'ps', '-a', '--format', '{{.Names}}'], capture_output=True, text=True, check=True)
            if result.returncode != 0:
                await interaction.response.send_message(f'Error encountered during docker ps -a command - see service logs.', ephemeral=True, delete_after=30)
                return

            containers = result.stdout.strip().splitlines()
            logger.debug(f'Found containers: {containers}')
            container_status = []
            sections = {}

            def split_containers(input_list):
                return [input_list[i:i + 2] for i in range(0, len(input_list), 2)]

            for container in containers:
                if container:
                    inspect = subprocess.run(['docker', 'inspect', '--format', '{{.State.Status}},{{.Config.Labels.section}}', container], capture_output=True, text=True, check=True)
                    status, section = inspect.stdout.strip().split(',')
                    section = section if section else "Uncategorized"
                    container_status.append(f'{container}')

                    if section not in sections:
                        sections[section] = []
                    sections[section].append([container, status.capitalize()])


            formatted_list = split_containers(container_status)
            formatted_list.sort()
            logger.debug(f'{formatted_list}')
            logger.debug(f'Container status: {container_status}')

            if not container_status:
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
                        await interaction.response.send_message(embeds=chunk)
                    else:
                        await interaction.followup.send(embeds=chunk)

        except subprocess.CalledProcessError as e:
            logger.error(f'Error executing docker command: {e}')
            await interaction.response.send_message(f'Error encountered in dockerlist - see service logs.', ephemeral=True, delete_after=30)

async def setup(bot):
  await bot.add_cog(ListContainers(bot))