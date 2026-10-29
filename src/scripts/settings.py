import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = {
    "AdminIDs": [],
    "AllowedRoles": {},
    "Sections": []
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
    print("ok")