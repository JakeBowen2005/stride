"""Private content-addressed FIT storage. Database bytes remain a local fallback."""
import hashlib
from app.config import settings


def _client():
    import boto3
    from botocore.config import Config
    return boto3.client('s3',use_ssl=True,config=Config(connect_timeout=5,read_timeout=30,retries={'max_attempts':2}))


def put_fit(user_id,blob):
    digest=hashlib.sha256(blob).hexdigest()
    key=f'{settings.fit_blob_prefix.strip("/")}/athletes/{user_id}/fit/{digest}.fit'
    _client().put_object(Bucket=settings.fit_blob_bucket,Key=key,Body=blob,ServerSideEncryption='AES256',ContentType='application/octet-stream')
    return key,digest


def read_fit(revision,user_id):
    if revision.fit_bytes is not None:
        return revision.fit_bytes
    prefix=f'{settings.fit_blob_prefix.strip("/")}/athletes/{user_id}/fit/'
    if not revision.fit_blob_key or not revision.fit_blob_key.startswith(prefix):
        raise ValueError('FIT evidence belongs to a different athlete or store')
    body=_client().get_object(Bucket=settings.fit_blob_bucket,Key=revision.fit_blob_key)['Body']
    try:
        blob=body.read(10*1024**2+1)
    finally:
        body.close()
    if len(blob)>10*1024**2 or hashlib.sha256(blob).hexdigest()!=revision.fit_sha256:
        raise ValueError('FIT evidence checksum mismatch')
    return blob
