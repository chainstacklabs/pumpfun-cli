import pytest

from pumpfun_cli.protocol.client import RpcClient


def test_client_creation():
    client = RpcClient("https://example.com")
    assert client is not None


def test_client_requires_url():
    with pytest.raises(TypeError):
        RpcClient()


def test_send_tx_accepts_confirm_parameter():
    import inspect

    from pumpfun_cli.protocol.client import RpcClient

    sig = inspect.signature(RpcClient.send_tx)
    assert "confirm" in sig.parameters
    assert sig.parameters["confirm"].default is False
