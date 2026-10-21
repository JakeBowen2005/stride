"""Offline regressions for the real container startup probe."""
import http.client
import importlib.util
from pathlib import Path
import urllib.error
from unittest.mock import MagicMock

import pytest

_spec = importlib.util.spec_from_file_location(
    'stride_container_smoke', Path(__file__).resolve().parents[2] / 'deploy/container_smoke.py')
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_startup_probe_retries_transient_socket_and_readiness_failures(monkeypatch):
    ready = MagicMock()
    ready.__enter__.return_value.status = 200
    outcomes = iter([ConnectionResetError('port not listening yet'),
                     http.client.RemoteDisconnected('startup connection closed'),
                     urllib.error.HTTPError('http://synthetic/healthz', 503, 'not ready', {}, None),
                     TimeoutError('still starting'), ready])
    calls = []

    def request(url, timeout):
        calls.append((url, timeout))
        result = next(outcomes)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(smoke.urllib.request, 'urlopen', request)
    monkeypatch.setattr(smoke.time, 'sleep', lambda _: None)
    smoke.wait_for_readiness('http://synthetic', attempts=5)
    assert calls == [('http://synthetic/healthz', 3)] * 5


def test_startup_probe_never_hides_permanently_unready_container(monkeypatch):
    calls = []

    def request(url, timeout):
        calls.append(url)
        raise ConnectionResetError('failed startup')

    monkeypatch.setattr(smoke.urllib.request, 'urlopen', request)
    monkeypatch.setattr(smoke.time, 'sleep', lambda _: None)
    with pytest.raises(RuntimeError, match='never became ready'):
        smoke.wait_for_readiness('http://synthetic', attempts=3)
    assert len(calls) == 3
