"""Credential isolation. Business transport awaits approved Garmin documentation."""
from datetime import datetime, timezone
from functools import lru_cache
from cryptography.fernet import Fernet, MultiFernet
from app.config import settings
from app.database import SessionLocal
from app.models.operations import ProviderCredential
from app.services.garmin_api import GarminNotConnected, PersonalApiClient


def cipher():
    keys=[k.strip() for k in settings.provider_encryption_keys.split(',') if k.strip()]
    if not keys:
        raise GarminNotConnected('Provider encryption key is not configured.')
    return MultiFernet([Fernet(k) for k in keys])


def configured(user_id,db):
    row=db.get(ProviderCredential,user_id)
    if row is not None:
        if row.kind == 'garmin_environment':
            return not row.revoked_at and user_id == settings.default_user_id and bool(settings.garmin_api_key.strip())
        return not row.revoked_at and bool(row.ciphertext) and (row.expires_at is None or row.expires_at>datetime.now(timezone.utc).replace(tzinfo=None))
    return user_id==settings.default_user_id and bool(settings.garmin_api_key.strip())


def connection_issue(user_id, db):
    """Actionable owner setup errors; never return provider secrets."""
    row = db.get(ProviderCredential, user_id)
    if row and row.revoked_at:
        return 'Garmin was disconnected in Stride. Reconnect in Settings to resume syncing.'
    if user_id != settings.default_user_id:
        return 'Separate Garmin accounts require Business API approval. Import FIT files in the meantime.'
    if row and row.kind == 'garmin_personal' and row.ciphertext:
        if row.expires_at and row.expires_at <= datetime.now(timezone.utc).replace(tzinfo=None):
            return 'The saved Garmin credential has expired. Reconnect in Settings.'
        if not settings.provider_encryption_keys:
            return 'The server cannot unlock the saved Garmin key. Restore STRIDE_PROVIDER_ENCRYPTION_KEYS in Render, or reconnect using the server key.'
    if not configured(user_id, db):
        return 'This server has no Garmin API key. Add GARMIN_API_KEY in Render Environment, save and redeploy, then sync again. A key in your Mac’s .env is not sent to Render.'
    return None


@lru_cache(maxsize=128)
def _personal_client(user_id,ciphertext):
    return PersonalApiClient(cipher().decrypt(ciphertext.encode()).decode())


@lru_cache(maxsize=1)
def _owner_client(key):
    return PersonalApiClient(key)


def client_for(user_id):
    with SessionLocal() as db:
        row=db.get(ProviderCredential,user_id)
        if row and configured(user_id,db):
            if row.kind == 'garmin_environment' and user_id == settings.default_user_id:
                return _owner_client(settings.garmin_api_key.strip())
            if row.kind!='garmin_personal' or user_id!=settings.default_user_id:
                raise GarminNotConnected('Garmin Business integration requires the approved application contract.')
            return _personal_client(user_id,row.ciphertext)
    if user_id==settings.default_user_id and row is None and settings.garmin_api_key.strip():
        return _owner_client(settings.garmin_api_key.strip())
    raise GarminNotConnected('Connect your approved Garmin account or import original FIT files.')
