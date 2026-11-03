import os
import discord
import logging
from discord import app_commands
from discord.ext import commands
from scripts.settings import load_settings, allowed_sections, remote_hosts, local_name
from scripts.containers import apply_settings, container_host, control, get_settings, list_all, permitted, resolve_hosts
from scripts import container_settings

logger = logging.getLogger(__name__)

DISCORD_GUILD_ID = os.environ.get('DISCORD_GUILD_ID')

class chooseActionView(discord.ui.View):
    def __init__(self, selected_container: str, editable=False, *, timeout=30):
        super().__init__(timeout=timeout)
        self.selected_container = selected_container
        self.add_item(selectAction(editable))

class ContainerPaginationView(discord.ui.View):
    def __init__(self, containers, timeout=30):
        super().__init__(timeout=timeout)
        self.containers = containers
        self.current_page = 0
        self.items_per_page = 24
        self.total_pages = (len(containers) - 1) // self.items_per_page + 1
        
        logger.debug(f"Creating pagination view with {len(containers)} containers")
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
            prev_button = discord.ui.Button(
                label="Previous",
                style=discord.ButtonStyle.gray,
                disabled=(self.current_page == 0),
                custom_id="prev"
            )
            next_button = discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.gray,
                disabled=(self.current_page >= self.total_pages - 1),
                custom_id="next"
            )
            
            prev_button.callback = self.prev_callback
            next_button.callback = self.next_callback
            self.add_item(prev_button)
            self.add_item(next_button)

    async def prev_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

    async def next_callback(self, interaction: discord.Interaction):
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        self.update_select_menu()
        await interaction.response.edit_message(view=self)

async def run_action(interaction: discord.Interaction, container_name: str, action: str):
    """Re-check permission, run the docker action and report it. The interaction must already be responded to."""
    # Re-check permission at action time: settings may have changed since the menu was shown.
    try:
        settings = load_settings() or {}
        allowed = allowed_sections(settings, interaction.user) if settings else set()
        local = local_name(settings)
        hosts = await resolve_hosts(remote_hosts(settings), local)
        containers = await list_all(hosts)
    except (RuntimeError, ValueError) as e:
        logger.error(f'Error checking permission: {e}')
        await interaction.followup.send('Error checking permission - see service logs.', ephemeral=True)
        return
    host = container_host(container_name, local)
    # A host that returned no containers didn't answer (named hosts skip the /info lookup, so `hosts` can't tell)
    if host != local and not any(container_host(c[0], local) == host for c in containers):
        logger.warning(f'{interaction.user} ({interaction.user.id}) {action} on {container_name} failed: {host} unreachable')
        await interaction.followup.send(f'{host} is unreachable - try again later.', ephemeral=True)
        return
    if container_name not in [c[0] for c in permitted(containers, allowed, local)]:
        logger.warning(f'{interaction.user} ({interaction.user.id}) denied {action} on {container_name}: no permission')
        await interaction.followup.send(f'You do not have permission to control {container_name}', ephemeral=True)
        return

    code, err = await control(container_name, action, hosts)
    if code != 0:
        logger.error(f'{container_name} failed to {action}: {err}')
        await interaction.followup.send(f'{interaction.user.mention} failed to {action} {container_name} - see service logs.')
        return
    past = {'start': 'started', 'stop': 'stopped', 'restart': 'restarted'}[action]
    logger.info(f'{container_name} successfully {past}')
    await interaction.followup.send(f'{interaction.user.mention} {container_name} has been {past}')

class confirmStopView(discord.ui.View):
    def __init__(self, container_name: str, *, timeout=30):
        super().__init__(timeout=timeout)
        self.container_name = container_name

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=f'Stopping {self.container_name}...', view=None)
        await run_action(interaction, self.container_name, 'stop')

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        logger.info(f'{interaction.user} ({interaction.user.id}) cancelled stop on {self.container_name}')
        await interaction.response.edit_message(content=f'Cancelled - {self.container_name} was not stopped.', view=None)

class selectAction(discord.ui.Select):
    def __init__(self, editable=False):
        options=[
            discord.SelectOption(label="Start",emoji="🟢",description="Start the selected container."),
            discord.SelectOption(label="Stop",emoji="🛑",description="Stop the selected container."),
            discord.SelectOption(label="Restart",emoji="🔄",description="Restart the selected container.")
            ]
        if editable:
            options.append(discord.SelectOption(label="Settings", emoji="⚙️", description="Change this container's settings."))
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
        # User ID too: usernames can change, IDs can't
        logger.info(f'{interaction.user} ({interaction.user.id}) requested {action} on {container_name}')

        if action == 'stop':
            await interaction.response.send_message(f'Stop **{container_name}**?', view=confirmStopView(container_name), ephemeral=True, delete_after=30)
            return
        if action == 'settings':
            await interaction.response.defer(ephemeral=True)
            await open_settings(interaction, container_name)
            return

        await interaction.response.defer()
        await run_action(interaction, container_name, action)

class selectContainerName(discord.ui.Select):
    def __init__(self, containers):
        self.by_name = {c[0]: c for c in containers}
        options = [
            # Value keeps "<host>/"; the label drops it since the host was picked already (or there is only one)
            discord.SelectOption(label=name.rpartition('/')[2], value=name, description=state.capitalize(), emoji="🟢" if state == "running" else "🛑")
            for name, state, *_ in containers
        ]
        super().__init__(placeholder="Select a container", max_values=1, min_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        name, state, _, image, _ = container = self.by_name[self.values[0]]
        await interaction.response.defer(ephemeral=True)
        action_view = chooseActionView(name, may_edit(interaction.user, container))
        header = f'**{name}** · {state}' + (f' · `{image}`' if image else '')
        action_message = await interaction.followup.send(header, view=action_view, ephemeral=True, wait=True)
        await action_message.delete(delay=30)

def may_edit(user, container):
    """Whether to offer Settings: editing is on, the container has a dcc.edit label, and EditRoles covers the user."""
    settings = load_settings() or {}
    if settings.get('EnableSettingsEditing') is not True or not container_settings.parse_edit(container[4]):
        return False
    try:
        return bool(permitted([container], allowed_sections(settings, user, 'EditRoles'), local_name(settings)))
    except ValueError as e:
        logger.error(f'Error checking edit permission: {e}')
        return False

async def edit_context(interaction: discord.Interaction, name: str):
    """Fresh (spec, hosts) if the user may still edit `name`; otherwise tells them why and returns None.
    The interaction must already be responded to."""
    try:
        settings = load_settings() or {}
        hosts = await resolve_hosts(remote_hosts(settings), local_name(settings))
        container = next((c for c in await list_all(hosts) if c[0] == name), None)
    except (RuntimeError, ValueError) as e:
        logger.error(f'Error checking edit permission: {e}')
        await interaction.followup.send('Error checking permission - see service logs.', ephemeral=True)
        return None
    if container is None:
        await interaction.followup.send(f'{name} is unreachable or no longer exists - try again later.', ephemeral=True)
        return None
    if not may_edit(interaction.user, container):
        logger.warning(f'{interaction.user} ({interaction.user.id}) denied settings on {name}: no permission')
        await interaction.followup.send(f'You do not have permission to change the settings of {name}', ephemeral=True)
        return None
    return container_settings.parse_edit(container[4]), hosts

async def open_settings(interaction: discord.Interaction, name: str):
    context = await edit_context(interaction, name)
    if not context:
        return
    spec, hosts = context
    try:
        values = await get_settings(name, hosts) if '/' in name else container_settings.read_values(name)
    except RuntimeError as e:
        logger.error(f'Error reading settings of {name}: {e}')
        await interaction.followup.send(f'Could not read the settings of {name} - see service logs.', ephemeral=True)
        return
    current = '\n'.join(f'{var}: `{values.get(var, "default")}`' for var in spec)
    message = await interaction.followup.send(
        f'**{name}** settings\n{current}\n\n**Apply & restart** restarts {name}: anyone connected to it is disconnected.',
        view=settingsView(name, spec, values), ephemeral=True, wait=True)
    await message.delete(delay=120)

class settingSelect(discord.ui.Select):
    def __init__(self, var, options, current):
        self.var = var
        super().__init__(placeholder=f'{var}: {current or "default"}'[:150], max_values=1, min_values=1,
                         options=[discord.SelectOption(label=o, default=(o == current)) for o in options])

    async def callback(self, interaction: discord.Interaction):
        self.view.chosen[self.var] = self.values[0]
        await interaction.response.defer()

class settingsView(discord.ui.View):
    def __init__(self, name, spec, values, *, timeout=120):
        super().__init__(timeout=timeout)
        self.name, self.chosen = name, {}
        for var, options in spec.items():
            self.add_item(settingSelect(var, options, values.get(var)))
        apply = discord.ui.Button(label='Apply & restart', style=discord.ButtonStyle.danger)
        apply.callback = self.apply
        self.add_item(apply)

    async def apply(self, interaction: discord.Interaction):
        if not self.chosen:
            await interaction.response.send_message('Pick a new value first.', ephemeral=True, delete_after=10)
            return
        await interaction.response.edit_message(content=f'Applying settings to **{self.name}**...', view=None)
        await run_apply(interaction, self.name, dict(self.chosen))

async def run_apply(interaction: discord.Interaction, name: str, values: dict):
    """Re-check edit permission, save the values and restart the container, and report it."""
    logger.info(f'{interaction.user} ({interaction.user.id}) requested settings {values} on {name}')
    context = await edit_context(interaction, name)
    if not context:
        return
    spec, hosts = context
    # Remote: the agent re-checks the values against its own label
    code, err = await (apply_settings(name, values, hosts) if '/' in name else container_settings.apply(name, values, spec))
    changes = ', '.join(f'{k}={v}' for k, v in values.items())
    if code != 0:
        logger.error(f'{name} failed to apply settings {values}: {err}')
        # A failed restart still leaves the values saved: they apply at the container's next start
        result = 'saved the settings, but could not restart' if 'saved, but restart failed' in err else 'failed to apply settings to'
        await interaction.followup.send(f'{interaction.user.mention} {result} {name} - see service logs.')
        return
    logger.info(f'{name} restarted with settings {values}')
    await interaction.followup.send(f'{interaction.user.mention} {name} has been restarted with {changes}')

class selectHost(discord.ui.Select):
    def __init__(self, by_host):
        self.by_host = by_host
        # shortcut: Discord allows 25 options per select; more than 25 hosts would need paging here too
        options = [discord.SelectOption(label=host, description=f'{len(c)} container(s)') for host, c in list(by_host.items())[:25]]
        super().__init__(placeholder="Select a host", max_values=1, min_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ContainerPaginationView(self.by_host[self.values[0]]))

class chooseHostView(discord.ui.View):
    def __init__(self, by_host, *, timeout=30):
        super().__init__(timeout=timeout)
        self.add_item(selectHost(by_host))

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

            local = local_name(settings)
            hosts = await resolve_hosts(remote_hosts(settings), local)
            containers = permitted(await list_all(hosts), allowed, local)

            if not containers:
                await interaction.response.send_message('No containers available to control.', ephemeral=True)
                return

            containers.sort()
            logger.debug(f'Filtered containers by permission: {containers}')
            by_host = {}
            for c in containers:
                by_host.setdefault(container_host(c[0], local), []).append(c)
            # Host step only when it saves scrolling: the user can see containers on 2+ hosts. Local host first.
            by_host = dict(sorted(by_host.items(), key=lambda kv: (kv[0] != local, kv[0])))
            view = chooseHostView(by_host) if len(by_host) > 1 else ContainerPaginationView(containers)

            await interaction.response.send_message(view=view, ephemeral=True, delete_after=30)

        except (RuntimeError, ValueError) as e:
            logger.error(f'Error building container list: {e}')
            await interaction.response.send_message(
                'Error retrieving container list - see service logs.',
                ephemeral=True
            )

async def setup(bot):
  await bot.add_cog(controlContainers(bot))