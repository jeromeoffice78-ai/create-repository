"""Read-only UnlockBase XML API v3 adapter. No billable actions are exposed."""
import os
import httpx
from defusedxml import ElementTree

ENDPOINT = 'https://www.unlockbase.com/xml/api/v3'
ALLOWED = {'AccountInfo', 'GetTools', 'GetOrders'}

class ProviderError(Exception):
    pass

async def query(action, parameters=None):
    if action not in ALLOWED:
        raise ProviderError('Action not enabled')
    key = os.getenv('UNLOCKBASE_API_KEY', '')
    if not key:
        raise ProviderError('Provider credential is not configured')
    fields = dict(parameters or {})
    if set(fields) - {'ID'} or ('ID' in fields and not str(fields['ID']).isdigit()):
        raise ProviderError('Invalid query parameters')
    fields.update(Key=key, Action=action)
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            response = await client.post(ENDPOINT, data=fields)
        response.raise_for_status()
        if len(response.content) > 4_000_000:
            raise ProviderError('Provider response too large')
        root = ElementTree.fromstring(response.content)
    except ProviderError:
        raise
    except Exception:
        raise ProviderError('Provider connection or XML response failed') from None
    if root.tag != 'API':
        raise ProviderError('Unexpected provider response')
    if root.find('Error') is not None:
        # Vendor errors may contain credentials or request data. Never forward them.
        raise ProviderError('UnlockBase rejected the request; check account and IP restrictions')
    return root
