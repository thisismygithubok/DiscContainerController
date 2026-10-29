import os
import asyncio

# shortcut: Docker sets HOSTNAME to the 12-char container ID; a custom `hostname:` in compose makes the bot list itself again.
SELF_ID = os.environ.get('HOSTNAME', '')

async def docker(*args):
    """Run a docker CLI command without blocking the event loop. Returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        'docker', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(), err.decode()

def parse_ps(output, self_id=''):
    """Parse `docker ps` lines of ID, name, state and section, leaving out the bot's own container."""
    containers = []
    for line in output.splitlines():
        if line:
            container_id, name, state, section = line.split('\t', 3)
            if container_id != self_id:
                containers.append((name, state, section or 'Uncategorized'))
    return containers

async def list_containers():
    """All containers except the bot itself as [(name, state, section)]. Raises RuntimeError if docker fails."""
    code, out, err = await docker('ps', '-a', '--format', '{{.ID}}\t{{.Names}}\t{{.State}}\t{{.Label "section"}}')
    if code != 0:
        raise RuntimeError(err.strip())
    return parse_ps(out, SELF_ID)

def permitted(containers, allowed):
    """Containers in the allowed sections; allowed=None means admin (everything)."""
    return [c for c in containers if allowed is None or c[2] in allowed]

if __name__ == "__main__":
    parsed = parse_ps("aaa\tweb\trunning\tGame Servers\nbbb\tdb\texited\t\nccc\tbot\trunning\tBackend\n\n", 'ccc')
    assert parsed == [('web', 'running', 'Game Servers'), ('db', 'exited', 'Uncategorized')], parsed
    assert permitted(parsed, None) == parsed
    assert permitted(parsed, {'Game Servers'}) == [parsed[0]]
    assert permitted(parsed, set()) == []
    print("ok")
