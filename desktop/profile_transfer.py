"""Bounded, data-only profile interchange; imported data never runs by itself."""
import json

MAX_BYTES = 1_000_000
MAX_PROFILES = 100
FORMAT = 'sacred-tweaks-profile-bundle'


def validate_profile_bundle(data: bytes):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ValueError('Profile file is too large or invalid.')
    try:
        bundle = json.loads(data.decode('utf-8'))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('Profile file must be valid UTF-8 JSON.') from exc
    if not isinstance(bundle, dict) or set(bundle) != {'format', 'version', 'profiles'} or bundle['format'] != FORMAT or bundle['version'] != 1:
        raise ValueError('Unsupported profile file format.')
    profiles = bundle['profiles']
    if not isinstance(profiles, list) or not profiles or len(profiles) > MAX_PROFILES:
        raise ValueError('Profile file must contain between 1 and 100 profiles.')
    clean = []
    names = set()
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {'name', 'config'}:
            raise ValueError('Profile entry contains unsupported fields.')
        name, config = item['name'], item['config']
        if not isinstance(name, str) or not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError('Profile name is invalid.')
        if name.casefold() in names:
            raise ValueError('Profile names in the file must be unique.')
        names.add(name.casefold())
        if not isinstance(config, dict) or set(config) != {'kind', 'config'}:
            raise ValueError('Profile configuration is invalid.')
        kind, values = config['kind'], config['config']
        if not isinstance(kind, str) or not isinstance(values, dict):
            raise ValueError('Profile configuration is invalid.')
        from desktop.macros import validate_config
        try:
            validate_config(kind, values)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError('Profile contains unsupported macro settings.') from exc
        clean.append({'name': name, 'config': {'kind': kind, 'config': values}})
    return clean


def encode_profile_bundle(profiles):
    normalized=[]
    for profile in profiles:
        normalized.append({'name': profile.get('name'), 'config': profile.get('config')})
    payload=json.dumps({'format':FORMAT,'version':1,'profiles':normalized},ensure_ascii=False,separators=(',',':')).encode('utf-8')
    validate_profile_bundle(payload)
    return payload
