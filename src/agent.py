import os
import hmac
import discord
import logging
from aiohttp import web
from scripts.containers import ACTIONS, docker, list_containers

# Remote agent: lets a master DiscContainerController list/start/stop/restart this host's containers.
# Permissions are enforced by the master; the agent only checks the shared token.

discord.utils.setup_logging(level=logging.INFO, root=True)
logger = logging.getLogger(__name__)

AGENT_TOKEN = os.environ.get('AGENT_TOKEN', '')
AGENT_PORT = int(os.environ.get('AGENT_PORT', '8080'))

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
        return web.json_response(await list_containers())
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

app = web.Application(middlewares=[auth])
app.add_routes([web.get('/info', get_info), web.get('/containers', get_containers), web.post('/containers/{name}/{action}', post_action)])

logger.info(f"Starting agent on port {AGENT_PORT}...")
web.run_app(app, port=AGENT_PORT, access_log=None, print=None)
