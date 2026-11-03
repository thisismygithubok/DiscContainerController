import os
import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)

ACTIONS = ('start', 'stop', 'restart')
AGENT_TIMEOUT = aiohttp.ClientTimeout(total=15)

# shortcut: Docker sets HOSTNAME to the 12-char container ID; a custom `hostname:` in compose makes the bot list itself again.
SELF_ID = os.environ.get('HOSTNAME', '')

# The only docker commands ever run: keeps the bot within what the socket proxy in the README allows.
DOCKER_COMMANDS = {'ps', 'info', 'start', 'stop', 'restart'}

async def docker(*args):
    """Run a docker CLI command without blocking the event loop. Returns (returncode, stdout, stderr)."""
    if args[0] not in DOCKER_COMMANDS:
        raise ValueError(f'docker {args[0]} is not allowed')
    proc = await asyncio.create_subprocess_exec(
        'docker', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(), err.decode()

def parse_ps(output, self_id=''):
    """Parse `docker ps` lines of ID, name, state, image, dcc.edit label and section, leaving out the bot's own container."""
    containers = []
    for line in output.splitlines():
        if line:
            container_id, name, state, image, edit, section = line.split('\t', 5)
            if container_id != self_id:
                containers.append((name, state, section or 'Uncategorized', image, edit))
    return containers

async def list_containers():
    """All containers except the bot itself as [(name, state, section, image, dcc.edit label)]. Raises RuntimeError if docker fails."""
    code, out, err = await docker('ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Image}}\t{{.Label "dcc.edit"}}\t{{.Label "section"}}')
    if code != 0:
        raise RuntimeError(err.strip())
    return parse_ps(out, SELF_ID)

def describe(e):
    """Error text for logs. Never repr(): aiohttp response errors' repr includes the request headers, i.e. the agent token."""
    return f'{type(e).__name__}: {e}'

async def agent_request(host, method, path, body=None):
    """Call a remote agent ({"url", "token"} from settings SecondaryHosts). Returns (HTTP status, JSON body)."""
    headers = {'Authorization': f'Bearer {host["token"]}'}
    async with aiohttp.ClientSession(timeout=AGENT_TIMEOUT, headers=headers) as session:
        async with session.request(method, host['url'].rstrip('/') + path, json=body) as resp:
            return resp.status, await resp.json()

async def host_name(host):
    """The host's configured name, else the agent's docker host name."""
    if host.get('name'):
        return host['name']
    status, data = await agent_request(host, 'GET', '/info')
    if status != 200:
        raise RuntimeError(f'HTTP {status}: {data}')
    return data['name']

async def resolve_hosts(hosts, local):
    """{"<name>": host} for reachable agents. Name lookups that fail, and duplicate names, are logged and skipped."""
    names = await asyncio.gather(*(host_name(h) for h in hosts), return_exceptions=True)
    named = {}
    for host, name in zip(hosts, names):
        if isinstance(name, BaseException):
            logger.warning(f'Agent {host["url"]} unavailable, skipping its containers: {describe(name)}')
        elif not isinstance(name, str) or not name or '/' in name or name == local or name in named:
            logger.error(f'Agent {host["url"]} has an invalid or duplicate name {name!r}; set a unique "name" for it in SecondaryHosts')
        else:
            named[name] = host
    return named

async def list_remote(host_name, host):
    status, data = await agent_request(host, 'GET', '/containers')
    if status != 200:
        raise RuntimeError(f'HTTP {status}: {data}')
    containers = []
    for name, state, section, *extra in data:
        image, edit = (extra + ['', ''])[:2]  # v1.0.8 agents send only name, state and section: no image, no editing
        containers.append((f'{host_name}/{name}', state, section, image, edit))
    return containers

async def list_all(hosts):
    """Local containers plus each agent's as "<host>/<container>". Unreachable agents are logged and skipped."""
    containers = await list_containers()
    results = await asyncio.gather(*(list_remote(n, h) for n, h in hosts.items()), return_exceptions=True)
    for host_name, result in zip(hosts, results):
        if isinstance(result, BaseException):
            logger.warning(f'Agent {host_name} unavailable, skipping its containers: {describe(result)}')
        else:
            containers.extend(result)
    return containers

async def control(name, action, hosts):
    """Start/stop/restart a local container or a "<host>/<container>" on an agent. Returns (returncode, error)."""
    # Docker names can't contain '/', so everything before the last one is the host.
    host_name, _, container = name.rpartition('/')
    if not host_name:
        code, _, err = await docker(action, container)
        return code, err.strip()
    try:
        status, data = await agent_request(hosts[host_name], 'POST', f'/containers/{container}/{action}')
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
        return 1, describe(e)
    return (0, '') if status == 200 else (1, f'HTTP {status}: {data}')

async def get_settings(name, hosts):
    """Current values of an agent container's editable settings. Raises RuntimeError if the agent can't say."""
    host_name, _, container = name.rpartition('/')
    try:
        status, data = await agent_request(hosts[host_name], 'GET', f'/containers/{container}/settings')
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
        raise RuntimeError(describe(e)) from e
    if status != 200:
        raise RuntimeError(f'HTTP {status}: {data}')
    return data['values']

async def apply_settings(name, values, hosts):
    """Ask an agent to apply settings to one of its containers; it checks them against its own label. Returns (returncode, error)."""
    host_name, _, container = name.rpartition('/')
    try:
        status, data = await agent_request(hosts[host_name], 'POST', f'/containers/{container}/settings', {'values': values})
    except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
        return 1, describe(e)
    return (0, '') if status == 200 else (1, f'HTTP {status}: {data}')

def container_host(name, local):
    return name.rpartition('/')[0] or local

def permitted(containers, allowed, local):
    """Containers the allowed entries cover: "<section>" (any host), "<host>/<section>" or "<host>/*".
    allowed=None means admin (everything); local is the name of the bot's own host."""
    if allowed is None:
        return list(containers)
    return [c for c in containers if allowed & {c[2], f'{container_host(c[0], local)}/{c[2]}', f'{container_host(c[0], local)}/*'}]

if __name__ == "__main__":
    local = 'main'  # any name works; deliberately not the default, so these checks can't depend on it
    parsed = parse_ps("aaa\tweb\trunning\tnginx:1\tMODE=a,b\tGame Servers\nbbb\tdb\texited\tpg\t\t\nccc\tbot\trunning\tdcc\t\tBackend\n\n", 'ccc')
    assert parsed == [('web', 'running', 'Game Servers', 'nginx:1', 'MODE=a,b'), ('db', 'exited', 'Uncategorized', 'pg', '')], parsed
    try:
        asyncio.run(docker('run', '--privileged', 'x'))
        raise AssertionError('docker run was allowed')
    except ValueError:
        pass
    assert permitted(parsed, None, local) == parsed
    assert permitted(parsed, {'Game Servers'}, local) == [parsed[0]]
    assert permitted(parsed, set(), local) == []
    mixed = parsed + [('pi/hawser', 'running', 'Uncategorized', '', ''), ('pi/games', 'running', 'Game Servers', '', '')]
    assert permitted(mixed, {'Game Servers'}, local) == [mixed[0], mixed[3]]
    assert permitted(mixed, {'pi/*'}, local) == mixed[2:]
    assert permitted(mixed, {'pi/Game Servers'}, local) == [mixed[3]]
    assert permitted(mixed, {f'{local}/*'}, local) == parsed
    assert permitted(mixed, {f'{local}/Uncategorized'}, local) == [mixed[1]]

    async def fake_request(host, method, path):
        return (200, {'name': host['reported']}) if host['reported'] else (404, {'error': 'not found'})
    agent_request = fake_request
    hosts = [{'url': 'a', 'token': 't', 'name': 'pi'}, {'url': 'b', 'token': 't', 'reported': 'nas'},
             {'url': 'c', 'token': 't', 'reported': 'nas'}, {'url': 'd', 'token': 't', 'reported': None},
             {'url': 'e', 'token': 't', 'reported': local}, {'url': 'f', 'token': 't', 'reported': 'x/y'}]
    assert asyncio.run(resolve_hosts(hosts, local)) == {'pi': hosts[0], 'nas': hosts[1]}

    from aiohttp.client_reqrep import RequestInfo
    from multidict import CIMultiDict, CIMultiDictProxy
    from yarl import URL
    info = RequestInfo(URL('http://x'), 'GET', CIMultiDictProxy(CIMultiDict({'Authorization': 'Bearer SECRET'})), URL('http://x'))
    assert 'SECRET' not in describe(aiohttp.ContentTypeError(info, (), status=502, message='not json'))
    print("ok")
