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
        return not row.revoked_at and bool(row.ciphertext) and (row.expires_at is None or row.expires_at>datetime.now(timezone.utc).replace(tzinfo=None))
    return user_id==settings.default_user_id and bool(settings.garmin_api_key)


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
            if row.kind!='garmin_personal' or user_id!=settings.default_user_id:
                raise GarminNotConnected('Garmin Business integration requires the approved application contract.')
            return _personal_client(user_id,row.ciphertext)
    if user_id==settings.default_user_id and row is None and settings.garmin_api_key:
        return _owner_client(settings.garmin_api_key)
    raise GarminNotConnected('Connect your approved Garmin account or import original FIT files.')
