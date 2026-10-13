"""Razorpay gateway diagnostic errors do not leak provider response or keys."""
import asyncio
import logging
import httpx
import pytest
from fastapi import HTTPException

from app import saas

@pytest.mark.parametrize('status,message', [
    (400, 'upstream 400'), (401, 'upstream 401'), (403, 'upstream 403'),
    (429, 'request limit reached'),
])
def test_gateway_errors_are_actionable_and_redacted(monkeypatch, caplog, status, message):
    monkeypatch.setenv('RAZORPAY_KEY_ID', 'rzp_test_dummy')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET', 'never-log-this-test-secret')
    sensitive = 'private-user@example.org'
    req=httpx.Request('POST', 'https://api.razorpay.com/v1/orders')
    response=httpx.Response(status, request=req, json={
        'error': {'code': 'BAD_REQUEST_ERROR', 'description': sensitive}
    })
    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def request(self, *args, **kwargs): return response
    monkeypatch.setattr(saas.httpx, 'AsyncClient', lambda **kwargs: FakeClient())
    with caplog.at_level(logging.WARNING):
        with pytest.raises(HTTPException) as err:
            asyncio.run(saas.razorpay('POST', 'orders', json={'amount':100}))
    assert err.value.status_code in (502, 503)
    assert message in err.value.detail
    assert sensitive not in err.value.detail and sensitive not in caplog.text
    assert 'never-log-this-test-secret' not in caplog.text
    assert 'orders' in caplog.text and 'HTTP ' in caplog.text

def test_gateway_network_error_is_redacted(monkeypatch, caplog):
    monkeypatch.setenv('RAZORPAY_KEY_ID','rzp_test_dummy')
    monkeypatch.setenv('RAZORPAY_KEY_SECRET','do-not-log-network-secret')
    class BrokenClient:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return None
        async def request(self, *args, **kwargs):
            raise httpx.ConnectTimeout('private network diagnostics')
    monkeypatch.setattr(saas.httpx,'AsyncClient',lambda **kwargs:BrokenClient())
    with caplog.at_level(logging.WARNING):
        with pytest.raises(HTTPException) as e:
            asyncio.run(saas.razorpay('POST','orders',json={'amount':100}))
    assert e.value.status_code==502
    assert 'Could not connect to Razorpay' in e.value.detail
    assert 'private network diagnostics' not in caplog.text
    assert 'do-not-log-network-secret' not in caplog.text
