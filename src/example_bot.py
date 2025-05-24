import discord
from discord.ext import commands
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
logger.info("Setting up Discord intents")

bot = commands.Bot(command_prefix='$', intents=intents)
logger.info("Bot instance created")

@bot.event
async def on_ready():
    logger.info(f'Bot is ready and logged in as {bot.user}')

@bot.command()
async def test(ctx, arg):
    await ctx.send(f'Hello! {ctx.author.mention} + {arg}')

# @bot.command()
# async def test(ctx, arg):
#     logger.info(f"Test command executed by {ctx.author} with argument: {arg}")
#     await ctx.send(f'{arg} - {ctx.author.mention}')

logger.info("Starting Discord bot...")
bot.run('MTM3NTc0MTAwOTMxNjgwNjY1Ng.GGi_Lv.oCTJHOm1bD9HNy0BvNFIOR38K1i4ZuwSnXgKpc')