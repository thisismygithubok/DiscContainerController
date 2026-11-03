"""Settings users may edit on a container (its dcc.edit label), stored as KEY=VALUE files that dcc-env.sh exports
when the container starts. Applying = write the file + `docker restart`, so no Docker access beyond start/stop/restart."""
import os
import re
import logging
from pathlib import Path
from scripts.containers import docker, list_containers

logger = logging.getLogger(__name__)

SETTINGS_DIR = Path('/config/container-settings')
WRAPPER = Path(__file__).with_name('dcc-env.sh')
VAR = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
NAME = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]*')  # docker container names
MAX_VARS = 4  # Discord allows 5 rows per message; the Apply button uses one

def parse_edit(label):
    """dcc.edit label "VAR=a,b;VAR2=c" -> {"VAR": ["a", "b"], "VAR2": ["c"]}. Invalid entries are logged and skipped."""
    spec = {}
    for entry in filter(None, (e.strip() for e in label.split(';'))):
        var, sep, opts = entry.partition('=')
        var = var.strip()
        # Discord option values are at most 100 chars; line breaks would split the KEY=VALUE file
        options = [o.strip() for o in opts.split(',') if o.strip() and len(o.strip()) <= 100 and not set(o) & set('\r\n\0')]
        if not sep or not VAR.fullmatch(var) or not options:
            logger.error(f'Skipping invalid dcc.edit entry {entry!r}: expected VAR=value1,value2')
            continue
        # shortcut: Discord selects hold 25 options; more are cut off. Upgrade to paging if a list needs more
        spec[var] = options[:25]
    if len(spec) > MAX_VARS:
        logger.error(f'dcc.edit has {len(spec)} variables; only the first {MAX_VARS} are editable')
    return dict(list(spec.items())[:MAX_VARS])

def invalid(values, spec):
    """Why `values` can't be applied (a variable or value not in the label), or None if they can."""
    for var, value in values.items():
        if var not in spec:
            return f'{var} is not editable'
        if value not in spec[var]:
            return f'{value!r} is not an allowed value for {var}'
    return None

def container_dir(container):
    """The container's folder in SETTINGS_DIR. `container` can come from an agent request, so it must stay inside."""
    if not NAME.fullmatch(container):
        raise ValueError(f'invalid container name {container!r}')
    # The name check already rules out "/" and "..": also check the resolved path (and symlinks), as code scanners expect
    base = os.path.realpath(SETTINGS_DIR)
    path = os.path.realpath(os.path.join(base, container))
    if not path.startswith(base + os.sep):
        raise ValueError(f'invalid container name {container!r}')
    return Path(path)

def prepare(container):
    """Create the container's settings folder with an up-to-date dcc-env.sh, which its entrypoint needs to start."""
    d = container_dir(container)
    wrapper = d / WRAPPER.name
    try:
        d.mkdir(parents=True, exist_ok=True)
        if not wrapper.exists() or wrapper.read_bytes() != WRAPPER.read_bytes():
            wrapper.write_bytes(WRAPPER.read_bytes())
            wrapper.chmod(0o755)
    except PermissionError as e:
        # Docker creates a missing bind-mount folder as root, so the bot (uid 1000) can't write into it
        raise RuntimeError(f'Cannot write {d} ({e.strerror}); on the host run: sudo chown -R 1000 <that folder>') from e

async def prepare_labeled():
    """prepare() every local container that has a dcc.edit label. Errors are logged, not raised."""
    try:
        containers = await list_containers()
    except RuntimeError as e:
        logger.error(f'Cannot prepare settings folders: {e}')
        return
    for name, *_, edit in containers:
        if edit:
            try:
                prepare(name)
            except (RuntimeError, ValueError) as e:
                logger.error(str(e))

def read_values(container):
    """The values set for the container, as {VAR: value}; empty if none were set yet."""
    try:
        lines = (container_dir(container) / 'settings.env').read_text().splitlines()
    except FileNotFoundError:
        return {}
    return dict(line.split('=', 1) for line in lines if '=' in line)

def write_values(container, values):
    prepare(container)
    path = container_dir(container) / 'settings.env'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(''.join(f'{k}={v}\n' for k, v in values.items()))
    os.replace(tmp, path)  # atomic: the container never reads a half-written file

async def apply(container, values, spec):
    """Validate `values` against the label's spec, save them and restart the container. Returns (returncode, error)."""
    error = invalid(values, spec)
    if error:
        return 1, error
    # Keep earlier choices, but drop variables the label no longer lists
    merged = {k: v for k, v in {**read_values(container), **values}.items() if k in spec}
    try:
        write_values(container, merged)
    except (OSError, RuntimeError, ValueError) as e:
        return 1, str(e)
    code, _, err = await docker('restart', container)
    return code, err.strip()

if __name__ == "__main__":
    import asyncio, subprocess, tempfile
    logging.disable()  # the invalid cases below log errors on purpose
    assert parse_edit('MAPS=zm_zod, zm_genesis;GAME_MODE=zclassic') == {'MAPS': ['zm_zod', 'zm_genesis'], 'GAME_MODE': ['zclassic']}
    assert parse_edit('') == {} and parse_edit('NOEQUALS;1BAD=x;GOOD=;OK=y') == {'OK': ['y']}
    assert parse_edit('A=' + 'x' * 101 + ',ok') == {'A': ['ok']}
    assert list(parse_edit(';'.join(f'V{i}=x' for i in range(6)))) == ['V0', 'V1', 'V2', 'V3']
    spec = {'MAPS': ['zm_zod', 'zm_genesis'], 'MODE': ['a']}
    assert invalid({'MAPS': 'zm_zod'}, spec) is None
    assert invalid({'MAPS': 'zm_other'}, spec) and invalid({'SECRET': 'a'}, spec)

    with tempfile.TemporaryDirectory() as tmp:
        SETTINGS_DIR = Path(tmp)
        restarted = []
        async def fake_docker(*args):
            restarted.append(args)
            return 0, '', ''
        docker = fake_docker
        assert asyncio.run(apply('bo3', {'MAPS': 'zm_zod'}, spec)) == (0, '') and restarted == [('restart', 'bo3')]
        assert asyncio.run(apply('bo3', {'MODE': 'a'}, spec)) == (0, '')
        assert read_values('bo3') == {'MAPS': 'zm_zod', 'MODE': 'a'}, 'earlier choices are kept'
        assert asyncio.run(apply('bo3', {'MAPS': 'nope'}, spec))[0] == 1 and len(restarted) == 2, 'invalid value: no restart'
        assert asyncio.run(apply('bo3', {'MAPS': 'zm_genesis'}, {'MAPS': spec['MAPS']})) == (0, '')
        assert read_values('bo3') == {'MAPS': 'zm_genesis'}, 'variables dropped from the label are removed'
        (Path(tmp) / 'link').symlink_to('/etc')  # a symlinked folder must not lead outside either
        for bad in ('../x', '', '-rf', '..', 'a/b', 'link'):
            try:
                container_dir(bad)
                raise AssertionError(f'bad container name accepted: {bad!r}')
            except ValueError:
                pass

        # The wrapper exports only well-formed KEY=VALUE lines and never runs a value
        d = container_dir('bo3')
        (d / 'settings.env').write_text('MAPS=zm_zod\nTRICK=$(touch pwned);`touch pwned`\nEQ=a=b\n1BAD=x\nbad-key=y\nnoequals\nLAST=no newline')
        out = subprocess.run([str(d / 'dcc-env.sh'), 'env'], capture_output=True, text=True, cwd=tmp, env={'PATH': os.environ['PATH'], 'MAPS': 'from-compose'}).stdout
        env = dict(line.split('=', 1) for line in out.splitlines() if '=' in line)
        assert env['MAPS'] == 'zm_zod', 'settings.env overrides the compose value'
        assert env['TRICK'] == '$(touch pwned);`touch pwned`' and not (Path(tmp) / 'pwned').exists()
        assert env['EQ'] == 'a=b' and env['LAST'] == 'no newline'
        assert '1BAD' not in env and 'bad-key' not in env
        assert subprocess.run([str(d / 'dcc-env.sh'), 'sh', '-c', 'exit 7']).returncode == 7, 'exec passes the exit code through'
    print("ok")
