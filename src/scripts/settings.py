import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "AdminIDs": [],
    "AllowedRoles": {},
    "Sections": [],
    "LocalName": "primary-node",
    "SecondaryHosts": [],
    "EnableSettingsEditing": False,
    "EditRoles": {}
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

def allowed_sections(settings, user, key='AllowedRoles'):
    """Sections the user may see/control (key='EditRoles': edit settings of), or None if the user is an admin (all sections)."""
    # map(str): IDs may be written as JSON numbers or strings
    if str(user.id) in map(str, settings.get('AdminIDs', [])):
        return None
    roles = settings.get(key, {})
    if not isinstance(roles, dict):
        raise ValueError(f'{key} in settings.json must be an object of {{"<role id>": [sections]}}')
    allowed = set()
    for role in user.roles:
        allowed.update(roles.get(str(role.id), []))
    return allowed

def local_name(settings):
    """Name of the bot's own host, used in the host menu and "<host>/..." permissions."""
    name = settings.get('LocalName') or DEFAULT_SETTINGS['LocalName']
    if not isinstance(name, str) or '/' in name:
        raise ValueError('LocalName in settings.json must be a name without "/"')
    return name

def remote_hosts(settings):
    """Remote agents as [{"url", "token", optional "name"}]. An entry can give "token_env" (an env var name)
    instead of "token", keeping the token out of settings.json. Invalid entries are logged and skipped,
    so one bad host doesn't stop the bot controlling the others."""
    hosts = settings.get('SecondaryHosts', [])
    if not isinstance(hosts, list):
        raise ValueError('SecondaryHosts in settings.json must be a list of {"url": "...", "token_env": "<env var>", "name": "<optional>"}')
    resolved = []
    for h in hosts:
        # Log only the url: an invalid entry may still hold a token
        url = h.get('url') if isinstance(h, dict) else None
        if not url or not ('token' in h or 'token_env' in h) or '/' in str(h.get('name', '')):
            logger.error(f'Skipping SecondaryHosts entry {url!r}: it needs "url", "token_env" (or "token"), and a "name" without "/" if set')
        elif 'token_env' in h and not os.environ.get(h['token_env']):
            # Names the variable only; the token itself is never logged or shown
            logger.error(f'Skipping SecondaryHosts entry {url}: environment variable {h["token_env"]} is not set in the bot container')
        else:
            resolved.append({**h, 'token': os.environ[h['token_env']]} if 'token_env' in h else h)
    return resolved

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
            
            if 'Hosts' in current_settings:
                logger.warning('settings.json has "Hosts", which is ignored since v1.0.8: rename it to "SecondaryHosts" (a list, see README)')

            updated = False
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
    logging.disable()  # the skip cases below log errors on purpose
    from types import SimpleNamespace as NS
    user = NS(id=42, roles=[NS(id=7)])
    assert allowed_sections({'AdminIDs': [42]}, user) is None
    assert allowed_sections({'AdminIDs': ['42']}, user) is None
    assert allowed_sections({'AllowedRoles': {'7': ['Games']}}, user) == {'Games'}
    assert allowed_sections({'AllowedRoles': {'7': ['Games']}, 'EditRoles': {'7': ['pi/*']}}, user, 'EditRoles') == {'pi/*'}
    assert allowed_sections({'AllowedRoles': {'7': ['Games']}}, user, 'EditRoles') == set()
    try:
        allowed_sections({'AllowedRoles': []}, user)
        raise AssertionError('list AllowedRoles accepted')
    except ValueError:
        pass
    assert remote_hosts({}) == []
    assert remote_hosts({'SecondaryHosts': [{'url': 'u', 'token': 't'}]}) == [{'url': 'u', 'token': 't'}]
    assert local_name({}) == DEFAULT_SETTINGS['LocalName'] and local_name({'LocalName': 'server-pc'}) == 'server-pc'
    os.environ['DCC_TEST_TOKEN'] = 'from-env'
    assert remote_hosts({'SecondaryHosts': [{'url': 'u', 'token_env': 'DCC_TEST_TOKEN'}]})[0]['token'] == 'from-env'
    os.environ.pop('DCC_UNSET_TOKEN', None)
    good = {'url': 'ok', 'token': 't'}
    bad_entries = [{'url': 'u'}, {'url': 'u', 'token': 't', 'name': 'a/b'}, 'x', {'token': 't'}, {'url': 'u', 'token_env': 'DCC_UNSET_TOKEN'}]
    assert remote_hosts({'SecondaryHosts': bad_entries + [good]}) == [good], 'bad entries must be skipped, good ones kept'
    for bad in ({'a': {'url': 'u', 'token': 't'}}, 'x'):
        try:
            remote_hosts({'SecondaryHosts': bad})
            raise AssertionError(f'non-list SecondaryHosts accepted: {bad}')
        except ValueError:
            pass
    print("ok")