"""Private hosted credential boundary: authenticated Nooks verification only."""
import os
import time
from fastapi import FastAPI, HTTPException, Request
from .common import Authenticate, body, header, load_scope, verify_nooks


def create_app(*, signing_key, public_key, scope, clock=time.time):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    auth = Authenticate(public_key, clock)

    @app.get('/healthz')
    async def health():
        return {'ok': True, 'role': 'private-verifier'}

    async def authenticated(request, raw, signature=''):
        try:
            auth.verify(request, raw, signature)
        except Exception:
            raise HTTPException(403, 'Request rejected.') from None

    @app.post('/v1/ready')
    async def ready(request: Request):
        raw = await body(request)
        await authenticated(request, raw)
        if raw != b'':
            raise HTTPException(400, 'Request rejected.')
        return {'ready': bool(signing_key) and scope['not_before'] <= clock() < scope['expires_at']}

    @app.post('/v1/nooks/verify')
    async def verify(request: Request):
        raw = await body(request)
        try:
            signature = header(request, 'x-webhook-signature', 200)
        except ValueError:
            raise HTTPException(403, 'Request rejected.') from None
        await authenticated(request, raw, signature)
        try:
            return {'event': verify_nooks(raw, signature, signing_key, scope, clock())}
        except Exception:
            raise HTTPException(403, 'Event rejected.') from None

    return app


def from_environment():
    return create_app(signing_key=os.environ.get('NOOKS_SIGNING_KEY', ''),
        public_key=os.environ.get('RECEIVER_PUBLIC_KEY', ''), scope=load_scope(os.environ['CAPTURE_SCOPE']))
