import urllib.request
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pytest


@pytest.fixture(autouse=True)
def block_live_portal_requests(monkeypatch):
    original_urlopen = urlopen

    def guarded_urlopen(url, *args, **kwargs):
        target = url.full_url if isinstance(url, Request) else str(url)
        if urlparse(target).hostname == "api.portaldatransparencia.gov.br":
            pytest.fail(
                "Testes não podem fazer requisições reais ao Portal da Transparência."
            )
        return original_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)
