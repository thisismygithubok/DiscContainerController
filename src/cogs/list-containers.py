import os
import discord
import logging
from discord import app_commands
from discord.ext import commands
from scripts.settings import load_settings, allowed_sections
from scripts.containers import list_containers, permitted

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

# Discord limits: 4096 chars per embed description, 6000 chars and 10 embeds per message.
DESCRIPTION_LIMIT = 4000
MESSAGE_LIMIT = 6000
EMBEDS_PER_MESSAGE = 10

def build_embeds(sections):
    """One embed per section (split if a section's table is too long), as [Embed]."""
    width = max([20] + [len(name) for rows in sections.values() for name, _ in rows])
    header = f"{'Container Name':<{width}}  Status\n{'-' * width}  -------\n"
    embeds = []
    for section, rows in sorted(sections.items()):
        lines = [f"{name:<{width}}  {status}\n" for name, status in sorted(rows)]
        chunk = ''
        for line in lines + [None]:
            if line is None or len(header) + len(chunk) + len(line) + 8 > DESCRIPTION_LIMIT:
                embeds.append(discord.Embed(title=f"Section: {section}", description=f"```\n{header}{chunk}```", color=discord.Color.blue()))
                chunk = ''
            if line is not None:
                chunk += line
    return embeds

def pack_messages(embeds):
    """Group embeds into messages that fit Discord's per-message limits."""
    messages, current, size = [], [], 0
    for embed in embeds:
        if current and (len(current) == EMBEDS_PER_MESSAGE or size + len(embed) > MESSAGE_LIMIT):
            messages.append(current)
            current, size = [], 0
        current.append(embed)
        size += len(embed)
    if current:
        messages.append(current)
    return messages

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
                sections.setdefault(section, []).append((container, status.capitalize()))

            logger.debug(f'Container status: {sections}')

            if not sections:
                await interaction.response.send_message('No containers found.', ephemeral=True, delete_after=30)
                return

            for i, chunk in enumerate(pack_messages(build_embeds(sections))):
                if i == 0:
                    await interaction.response.send_message(embeds=chunk, ephemeral=True, delete_after=30)
                else:
                    message = await interaction.followup.send(embeds=chunk, ephemeral=True, wait=True)
                    await message.delete(delay=30)

        except (RuntimeError, ValueError, discord.HTTPException) as e:
            logger.error(f'Error in list-containers: {e}')
            send = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
            await send('Error listing containers - see service logs.', ephemeral=True)

async def setup(bot):
  await bot.add_cog(ListContainers(bot))

if __name__ == "__main__":
    # Run from src/: DISCORD_GUILD_ID=1 PYTHONPATH=. python3 cogs/list-containers.py
    big = {f'S{s}': [(f'container-{s}-{i}', 'Running') for i in range(150)] for s in range(3)}
    embeds = build_embeds(big)
    assert all(len(e.description) <= 4096 for e in embeds)
    assert sum(e.description.count('container-') for e in embeds) == 450
    messages = pack_messages(embeds)
    assert all(len(m) <= 10 and sum(len(e) for e in m) <= 6000 for m in messages)
    assert sum(len(m) for m in messages) == len(embeds)
    assert len(build_embeds({'A': [('web', 'Running')]})) == 1
    print("ok")
