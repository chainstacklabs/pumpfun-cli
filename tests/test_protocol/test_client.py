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


# --- TransactionFailedError tests ---


def test_transaction_failed_error_parses_slippage_code():
    """TransactionFailedError parses error_code and instruction_index from meta.err string."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    err_str = "TransactionErrorInstructionError((0, Tagged(InstructionErrorCustom(6002))))"
    exc = TransactionFailedError(err_str)
    assert exc.error_code == 6002
    assert exc.instruction_index == 0
    assert exc.raw_error == err_str


def test_transaction_failed_error_parses_unknown_format():
    """TransactionFailedError with non-matching string has None for parsed fields."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    err_str = "some unknown error format"
    exc = TransactionFailedError(err_str)
    assert exc.error_code is None
    assert exc.instruction_index is None
    assert exc.raw_error == err_str


def test_transaction_failed_error_inherits_runtime_error():
    """TransactionFailedError is a RuntimeError subclass."""
    from pumpfun_cli.protocol.client import TransactionFailedError

    exc = TransactionFailedError("test")
    assert isinstance(exc, RuntimeError)
