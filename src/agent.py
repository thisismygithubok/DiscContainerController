import os
import hmac
import discord
import logging
from aiohttp import web
from scripts.containers import ACTIONS, docker, list_containers
from scripts import container_settings

# Remote agent: lets a master DiscContainerController list/start/stop/restart this host's containers.
# Permissions are enforced by the master; the agent only checks the shared token.

discord.utils.setup_logging(level=logging.INFO, root=True)
logger = logging.getLogger(__name__)

AGENT_TOKEN = os.environ.get('AGENT_TOKEN', '')
AGENT_PORT = int(os.environ.get('AGENT_PORT', '8080'))
# Settings editing is opt-in per host, so a host's owner decides even if the master has it on
AGENT_ENABLE_EDIT = os.environ.get('AGENT_ENABLE_EDIT', '').lower() == 'true'

if len(AGENT_TOKEN) < 32:
    logger.error("AGENT_TOKEN must be at least 32 characters (e.g. `openssl rand -hex 32`)")
    raise ValueError("AGENT_TOKEN is required to run the agent")

@web.middleware
async def auth(request, handler):
    if not hmac.compare_digest(request.headers.get('Authorization', '').encode(), f'Bearer {AGENT_TOKEN}'.encode()):
        logger.warning(f'Rejected unauthorized {request.method} {request.path} from {request.remote}')
        return web.json_response({'error': 'unauthorized'}, status=401)
    return await handler(request)

async def get_containers(request):
    try:
        containers = await list_containers()
        # Without editing, hide dcc.edit labels so the master doesn't offer Settings for this host
        return web.json_response(containers if AGENT_ENABLE_EDIT else [c[:4] + ('',) for c in containers])
    except RuntimeError as e:
        logger.error(f'Error listing containers: {e}')
        return web.json_response({'error': str(e)}, status=500)

async def get_info(request):
    # Default display name for the master: the docker host's hostname, not this container's ID
    code, out, err = await docker('info', '--format', '{{.Name}}')
    if code != 0:
        logger.error(f'Error reading docker info: {err.strip()}')
        return web.json_response({'error': err.strip()}, status=500)
    return web.json_response({'name': out.strip()})

async def post_action(request):
    name, action = request.match_info['name'], request.match_info['action']
    if action not in ACTIONS:
        return web.json_response({'error': f'unknown action {action}'}, status=404)
    try:
        containers = await list_containers()
    except RuntimeError as e:
        logger.error(f'Error listing containers: {e}')
        return web.json_response({'error': str(e)}, status=500)
    # Only listed names: excludes the agent's own container and option-like names such as "--help"
    if name not in [c[0] for c in containers]:
        return web.json_response({'error': f'no container {name}'}, status=404)

    logger.info(f'{request.remote} requested {action} on {name}')
    code, _, err = await docker(action, name)
    if code != 0:
        logger.error(f'{name} failed to {action}: {err.strip()}')
        return web.json_response({'error': err.strip()}, status=500)
    logger.info(f'{name} {action} succeeded')
    return web.json_response({'ok': True})

async def edit_spec(name):
    """(spec, None) for a listed container with a dcc.edit label, else (None, error response)."""
    if not AGENT_ENABLE_EDIT:
        return None, web.json_response({'error': 'settings editing is disabled on this agent (AGENT_ENABLE_EDIT)'}, status=404)
    try:
        containers = await list_containers()
    except RuntimeError as e:
        logger.error(f'Error listing containers: {e}')
        return None, web.json_response({'error': str(e)}, status=500)
    spec = next((container_settings.parse_edit(c[4]) for c in containers if c[0] == name), None)
    if not spec:
        return None, web.json_response({'error': f'no editable container {name}'}, status=404)
    return spec, None

async def get_settings(request):
    spec, error = await edit_spec(request.match_info['name'])
    return error or web.json_response({'values': container_settings.read_values(request.match_info['name'])})

async def post_settings(request):
    name = request.match_info['name']
    spec, error = await edit_spec(name)
    if error:
        return error
    try:
        values = (await request.json())['values']
        assert isinstance(values, dict) and all(isinstance(v, str) for v in values.values())
    except (ValueError, KeyError, TypeError, AssertionError):
        return web.json_response({'error': 'expected {"values": {"VAR": "value"}}'}, status=400)
    logger.info(f'{request.remote} requested settings {values} on {name}')
    # Checked against this host's own label: the master's request is never trusted for what is editable
    code, err = await container_settings.apply(name, values, spec)
    if code != 0:
        logger.error(f'{name} settings failed: {err}')
        return web.json_response({'error': err}, status=400)
    logger.info(f'{name} restarted with new settings')
    return web.json_response({'ok': True})

async def prepare_settings(app):
    if AGENT_ENABLE_EDIT:
        await container_settings.prepare_labeled()

app = web.Application(middlewares=[auth])
# Settings routes first: /containers/{name}/{action} would otherwise match /containers/{name}/settings
app.add_routes([web.get('/info', get_info), web.get('/containers', get_containers),
                web.get('/containers/{name}/settings', get_settings), web.post('/containers/{name}/settings', post_settings),
                web.post('/containers/{name}/{action}', post_action)])
app.on_startup.append(prepare_settings)

logger.info(f"Starting agent on port {AGENT_PORT}...")
web.run_app(app, port=AGENT_PORT, access_log=None, print=None)
