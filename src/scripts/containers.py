import asyncio

async def docker(*args):
    """Run a docker CLI command without blocking the event loop. Returns (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        'docker', *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    return proc.returncode, out.decode(), err.decode()

def parse_ps(output):
    containers = []
    for line in output.splitlines():
        if line:
            name, state, section = line.split('\t', 2)
            containers.append((name, state, section or 'Uncategorized'))
    return containers

async def list_containers():
    """All containers as [(name, state, section)]. Raises RuntimeError if docker fails."""
    code, out, err = await docker('ps', '-a', '--format', '{{.Names}}\t{{.State}}\t{{.Label "section"}}')
    if code != 0:
        raise RuntimeError(err.strip())
    return parse_ps(out)

def permitted(containers, allowed):
    """Containers in the allowed sections; allowed=None means admin (everything)."""
    return [c for c in containers if allowed is None or c[2] in allowed]

if __name__ == "__main__":
    parsed = parse_ps("web\trunning\tGame Servers\ndb\texited\t\n\n")
    assert parsed == [('web', 'running', 'Game Servers'), ('db', 'exited', 'Uncategorized')], parsed
    assert permitted(parsed, None) == parsed
    assert permitted(parsed, {'Game Servers'}) == [parsed[0]]
    assert permitted(parsed, set()) == []
    print("ok")
