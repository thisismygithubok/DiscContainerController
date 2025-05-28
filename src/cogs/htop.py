import os
import discord
import logging
import subprocess
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class htop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(discord.Object(id=DISCORD_GUILD_ID)) # type: ignore
    @app_commands.command(name='htop', description='Captures HTOP and sends as screenshot')

    async def htop(self, interaction: discord.Interaction):
        try:
            htop_html = subprocess.run(['echo', 'q', '|', 'htop', '|', 'aha', '--black', '--line-fix', '>', '../htop.html'], capture_output=True, text=True, check=True)
            if htop_html.returncode != 0:
                await interaction.response.send_message(f'Error encountered htop html generation - see service logs.', ephemeral=True, delete_after=30)
                return
            htop_png = subprocess.run(['node', '../scripts/htop.js'], capture_output=True, text=True, check=True)
            if htop_png.returncode != 0:
                await interaction.response.send_message(f'Error encountered htop png generation - see service logs.', ephemeral=True, delete_after=30)
                return
        except subprocess.CalledProcessError as e:
            logger.error(f'Error executing htop command: {e}')
            await interaction.response.send_message(f'Error encountered in htop - see service logs.', ephemeral=True, delete_after=30)


async def setup(bot):
  await bot.add_cog(htop(bot))