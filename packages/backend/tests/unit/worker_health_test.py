import json

import pytest
from aiohttp.test_utils import make_mocked_request

from worker import _health


@pytest.mark.asyncio
async def test_worker_health_returns_200() -> None:
    response = await _health(make_mocked_request("GET", "/health"))
    assert response.status == 200
    body = json.loads(response.text)
    assert body == {"status": "healthy", "service": "worker"}
