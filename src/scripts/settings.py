import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "AdminIDs": [],
    "AllowedRoles": {},
    "Sections": [],
    "LocalName": "primary-node",
    "SecondaryHosts": []
}

CONFIG_PATH = Path("/config/settings.json")

def load_settings():
    """Read settings.json fresh so edits apply without a restart. Returns None on error."""
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f'Error loading settings: {e}')
        return None

def allowed_sections(settings, user):
    """Sections the user may see/control, or None if the user is an admin (all sections)."""
    # map(str): IDs may be written as JSON numbers or strings
    if str(user.id) in map(str, settings.get('AdminIDs', [])):
        return None
    roles = settings.get('AllowedRoles', {})
    if not isinstance(roles, dict):
        raise ValueError('AllowedRoles in settings.json must be an object of {"<role id>": [sections]}')
    allowed = set()
    for role in user.roles:
        allowed.update(roles.get(str(role.id), []))
    return allowed

def local_name(settings):
    """Name of the bot's own host, used in the host menu and "<host>/..." permissions."""
    name = settings.get('LocalName') or 'primary-node'
    if not isinstance(name, str) or '/' in name:
        raise ValueError('LocalName in settings.json must be a name without "/"')
    return name

def remote_hosts(settings):
    """Remote agents as [{"url", "token", optional "name"}]. The v1.0.7 form {"<name>": {...}} is still accepted."""
    hosts = settings.get('SecondaryHosts', [])
    if isinstance(hosts, dict):
        hosts = [{**h, 'name': name} if isinstance(h, dict) else h for name, h in hosts.items()]
    if not isinstance(hosts, list) or not all(
            isinstance(h, dict) and 'url' in h and 'token' in h and '/' not in str(h.get('name', '')) for h in hosts):
        raise ValueError('SecondaryHosts in settings.json must be a list of {"url": "...", "token": "...", "name": "<optional, no />"}')
    return hosts

def check_settings_file():
    config_path = CONFIG_PATH
    logger.info(f"Checking for settings file...")
    
    try:
        if not config_path.parent.exists():
            logger.debug("Creating config folder...")
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
        if not config_path.exists():
            logger.debug("Creating new settings.json with default values...")
            with open(config_path, 'w') as f:
                json.dump(DEFAULT_SETTINGS, f, indent=4)
        else:
            with open(config_path, 'r') as f:
                current_settings = json.load(f)
                logger.debug(f"Settings file already exists, loading...")
            
            updated = False
            # v1.0.7 called it "Hosts"; rename before defaults are filled in, or it would be shadowed by an empty SecondaryHosts
            if 'Hosts' in current_settings and 'SecondaryHosts' not in current_settings:
                current_settings['SecondaryHosts'] = current_settings.pop('Hosts')
                logger.info('Renamed "Hosts" to "SecondaryHosts" in settings.json')
                updated = True
            for key, value in DEFAULT_SETTINGS.items():
                if key not in current_settings:
                    current_settings[key] = value
                    updated = True
            
            if updated:
                logger.info("Updating settings.json user-defined values...")
                with open(config_path, 'w') as f:
                    json.dump(current_settings, f, indent=4)
            else:
                logger.info("Settings file is up-to-date")
                
    except Exception as e:
        logger.error(f"Error managing settings file: {e}")
        raise

if __name__ == "__main__":
    from types import SimpleNamespace as NS
    user = NS(id=42, roles=[NS(id=7)])
    assert allowed_sections({'AdminIDs': [42]}, user) is None
    assert allowed_sections({'AdminIDs': ['42']}, user) is None
    assert allowed_sections({'AllowedRoles': {'7': ['Games']}}, user) == {'Games'}
    try:
        allowed_sections({'AllowedRoles': []}, user)
        raise AssertionError('list AllowedRoles accepted')
    except ValueError:
        pass
    assert remote_hosts({}) == []
    assert remote_hosts({'SecondaryHosts': {'a': {'url': 'u', 'token': 't'}}}) == [{'url': 'u', 'token': 't', 'name': 'a'}]
    assert remote_hosts({'SecondaryHosts': [{'url': 'u', 'token': 't'}]}) == [{'url': 'u', 'token': 't'}]
    assert local_name({}) == 'primary-node' and local_name({'LocalName': 'server-pc'}) == 'server-pc'
    for bad in ({'a': {'url': 'u'}}, [{'url': 'u', 'token': 't', 'name': 'a/b'}], 'x'):
        try:
            remote_hosts({'SecondaryHosts': bad})
            raise AssertionError(f'bad SecondaryHosts accepted: {bad}')
        except ValueError:
            pass

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        CONFIG_PATH = Path(d) / 'settings.json'
        old_hosts = {'pi': {'url': 'u', 'token': 't'}}
        CONFIG_PATH.write_text(json.dumps({'AdminIDs': ['1'], 'Hosts': old_hosts}))
        check_settings_file()
        migrated = json.loads(CONFIG_PATH.read_text())
        assert 'Hosts' not in migrated and migrated['SecondaryHosts'] == old_hosts and migrated['AdminIDs'] == ['1'], migrated
        assert migrated['LocalName'] == 'primary-node'
    print("ok")