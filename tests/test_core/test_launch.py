"""Tests for core/launch.py — cashback flag pass-through."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_launch_passes_cashback_false(tmp_keystore):
    """launch_token passes is_cashback=False through to build_create_instructions."""
    with (
        patch(
            "pumpfun_cli.core.launch.upload_metadata",
            new_callable=AsyncMock,
            return_value="https://ipfs.example.com/metadata.json",
        ),
        patch("pumpfun_cli.core.launch.build_create_instructions", wraps=None) as mock_build,
        patch("pumpfun_cli.core.launch.build_extend_account_instruction"),
        patch(
            "pumpfun_cli.core.launch.RpcClient",
        ) as mock_rpc_cls,
    ):
        mock_client = AsyncMock()
        mock_client.send_tx = AsyncMock(return_value="fakesig123")
        mock_rpc_cls.return_value = mock_client

        # build_create_instructions needs to return a list of instructions
        from unittest.mock import MagicMock

        mock_ix = MagicMock()
        mock_build.return_value = [mock_ix]

        from pumpfun_cli.core.launch import launch_token

        result = await launch_token(
            rpc_url="https://fake.rpc",
            keystore_path=tmp_keystore,
            password="testpass",
            name="TestToken",
            ticker="TST",
            description="A test token",
            is_cashback=False,
        )

        mock_build.assert_called_once()
        call_kwargs = mock_build.call_args
        assert call_kwargs.kwargs.get("is_cashback") is False or (
            not call_kwargs.kwargs.get("is_cashback", True)
        )
        assert result["is_cashback"] is False


@pytest.mark.asyncio
async def test_launch_passes_cashback_true(tmp_keystore):
    """launch_token passes is_cashback=True through to build_create_instructions."""
    with (
        patch(
            "pumpfun_cli.core.launch.upload_metadata",
            new_callable=AsyncMock,
            return_value="https://ipfs.example.com/metadata.json",
        ),
        patch("pumpfun_cli.core.launch.build_create_instructions", wraps=None) as mock_build,
        patch("pumpfun_cli.core.launch.build_extend_account_instruction"),
        patch(
            "pumpfun_cli.core.launch.RpcClient",
        ) as mock_rpc_cls,
    ):
        mock_client = AsyncMock()
        mock_client.send_tx = AsyncMock(return_value="fakesig456")
        mock_rpc_cls.return_value = mock_client

        from unittest.mock import MagicMock

        mock_ix = MagicMock()
        mock_build.return_value = [mock_ix]

        from pumpfun_cli.core.launch import launch_token

        result = await launch_token(
            rpc_url="https://fake.rpc",
            keystore_path=tmp_keystore,
            password="testpass",
            name="TestToken",
            ticker="TST",
            description="A test token",
            is_cashback=True,
        )

        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["is_cashback"] is True
        assert result["is_cashback"] is True
