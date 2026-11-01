"""Pump.fun program IDs, system addresses, and constants."""

from solders.pubkey import Pubkey

# pump.fun's HTTP endpoints sit behind Cloudflare, which rejects the default
# python-httpx User-Agent; an identifying one is accepted.
HTTP_HEADERS = {"User-Agent": "pumpfun-cli (+https://github.com/chainstacklabs/pumpfun-cli)"}

# Solana constants
LAMPORTS_PER_SOL = 1_000_000_000
SOL_DECIMALS = 9
TOKEN_DECIMALS = 6  # every pump.fun coin has 6 decimals; other PumpSwap pools may not

# System programs
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOCIATED_TOKEN_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
RENT = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

# Pump.fun program addresses
PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMP_GLOBAL = Pubkey.from_string("4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf")
PUMP_EVENT_AUTHORITY = Pubkey.from_string("Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1")
PUMP_FEE_PROGRAM = Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")
PUMP_MINT_AUTHORITY = Pubkey.from_string("TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM")

# Mayhem mode addresses. create_v2 needs all of them whether or not the coin is
# a mayhem coin; the is_mayhem_mode argument is what makes it one.
MAYHEM_PROGRAM_ID = Pubkey.from_string("MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e")
MAYHEM_GLOBAL_PARAMS = Pubkey.from_string("13ec7XdrjF3h3YcqBTFDSReRcUFwbCnJaAQspM4j6DDJ")
MAYHEM_SOL_VAULT = Pubkey.from_string("BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s")

# PumpSwap AMM addresses
PUMP_AMM_PROGRAM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
PUMP_SWAP_GLOBAL_CONFIG = Pubkey.from_string("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw")
PUMP_SWAP_EVENT_AUTHORITY = Pubkey.from_string("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR")

# Quote assets. BondingCurve.quote_mint is all zeros for a SOL-paired coin, but
# every instruction takes wrapped SOL in that position.
DEFAULT_PUBKEY = Pubkey.default()
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
# Known without an RPC call. Any other quote mint is resolved from its account.
KNOWN_QUOTE_MINTS: dict[Pubkey, tuple[Pubkey, int]] = {
    WSOL_MINT: (TOKEN_PROGRAM, 9),
    USDC_MINT: (TOKEN_PROGRAM, 6),
}
# `decimals` sits at this offset in SPL Token and Token-2022 mints alike.
MINT_DECIMALS_OFFSET = 44

# Fee recipients for buy_v2 / sell_v2 / buy_exact_quote_in_v2: a normal one for
# ordinary coins, a reserved one for mayhem coins, and a buyback one on every
# trade. Picked at random per transaction to spread write contention.
NORMAL_FEE_RECIPIENTS = [
    Pubkey.from_string("62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV"),
    Pubkey.from_string("7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ"),
    Pubkey.from_string("7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX"),
    Pubkey.from_string("9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz"),
    Pubkey.from_string("AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY"),
    Pubkey.from_string("CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM"),
    Pubkey.from_string("FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz"),
    Pubkey.from_string("G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP"),
]
RESERVED_FEE_RECIPIENTS = [
    Pubkey.from_string("GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS"),
    Pubkey.from_string("4budycTjhs9fD6xw62VBducVTNgMgJJ5BgtKq7mAZwn6"),
    Pubkey.from_string("8SBKzEQU4nLSzcwF4a74F2iaUDQyTfjGndn6qUWBnrpR"),
    Pubkey.from_string("4UQeTP1T39KZ9Sfxzo3WR5skgsaP6NZa87BAkuazLEKH"),
    Pubkey.from_string("8sNeir4QsLsJdYpc9RZacohhK1Y5FLU3nC5LXgYB4aa6"),
    Pubkey.from_string("Fh9HmeLNUMVCvejxCtCL2DbYaRyBFVJ5xrWkLnMH6fdk"),
    Pubkey.from_string("463MEnMeGyJekNZFQSTUABBEbLnvMTALbT6ZmsxAbAdq"),
    Pubkey.from_string("6AUH3WEHucYZyC61hqpqYUWVto5qA5hjHuNQ32GNnNxA"),
]
BUYBACK_FEE_RECIPIENTS = [
    Pubkey.from_string("5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD"),
    Pubkey.from_string("9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7"),
    Pubkey.from_string("GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL"),
    Pubkey.from_string("3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR"),
    Pubkey.from_string("5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6"),
    Pubkey.from_string("EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL"),
    Pubkey.from_string("5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD"),
    Pubkey.from_string("A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"),
]

# pump.fun instruction discriminators
BUY_V2_DISCRIMINATOR = bytes([184, 23, 238, 97, 103, 197, 211, 61])
SELL_V2_DISCRIMINATOR = bytes([93, 246, 130, 60, 231, 233, 64, 178])
BUY_EXACT_QUOTE_IN_V2_DISCRIMINATOR = bytes([194, 171, 28, 70, 104, 77, 91, 47])
CREATE_V2_DISCRIMINATOR = bytes([214, 144, 76, 236, 95, 139, 49, 180])
EXTEND_ACCOUNT_DISCRIMINATOR = bytes([234, 102, 194, 203, 150, 72, 62, 229])
COLLECT_CREATOR_FEE_V2_DISCRIMINATOR = bytes([207, 17, 138, 242, 4, 34, 19, 56])
CLAIM_CASHBACK_V2_DISCRIMINATOR = bytes([122, 243, 204, 65, 94, 116, 29, 55])
CLOSE_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR = bytes([249, 69, 164, 218, 150, 103, 84, 138])
MIGRATE_V2_DISCRIMINATOR = bytes([187, 203, 18, 31, 206, 237, 254, 41])

# PumpSwap instruction discriminators
PUMPSWAP_BUY_DISCRIMINATOR = bytes([102, 6, 61, 18, 1, 218, 235, 234])
PUMPSWAP_SELL_DISCRIMINATOR = bytes([51, 230, 133, 164, 1, 127, 131, 173])
PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR = bytes([198, 46, 21, 82, 180, 217, 232, 112])
COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR = bytes([160, 57, 89, 42, 181, 139, 43, 66])
PUMPSWAP_INIT_USER_VOLUME_ACCUMULATOR_DISCRIMINATOR = bytes([94, 6, 202, 115, 255, 96, 232, 183])

# Account discriminators
BONDING_CURVE_DISCRIMINATOR = bytes([23, 183, 248, 55, 96, 216, 172, 96])
GLOBAL_DISCRIMINATOR = bytes([167, 232, 232, 177, 200, 108, 114, 127])
QUOTE_CONTROL_DISCRIMINATOR = bytes([56, 244, 35, 238, 193, 213, 162, 201])
POOL_DISCRIMINATOR = bytes([241, 154, 109, 4, 17, 177, 109, 188])
GLOBAL_CONFIG_DISCRIMINATOR = bytes([149, 8, 156, 202, 160, 252, 176, 217])

# PumpSwap Pool offsets, discriminator included. Live pools are 301 bytes.
POOL_BASE_MINT_OFFSET = 43
POOL_COIN_CREATOR_OFFSET = 211
POOL_MAYHEM_MODE_OFFSET = 243
POOL_CASHBACK_OFFSET = 244
POOL_VIRTUAL_QUOTE_RESERVES_OFFSET = 245  # i128, added to the quote vault when pricing

# PumpSwap GlobalConfig offsets, discriminator included.
GLOBALCONFIG_LP_FEE_BPS_OFFSET = 40
GLOBALCONFIG_PROTOCOL_FEE_BPS_OFFSET = 48
GLOBALCONFIG_PROTOCOL_FEE_RECIPIENTS_OFFSET = 57  # 8 pubkeys
GLOBALCONFIG_COIN_CREATOR_FEE_BPS_OFFSET = 313
GLOBALCONFIG_RESERVED_FEE_RECIPIENT_OFFSET = 385  # the one mayhem pools pay
GLOBALCONFIG_BUYBACK_FEE_RECIPIENTS_OFFSET = 643  # 8 pubkeys

# Solana rent / fee constants
SOL_RENT_EXEMPT_MIN = 890_880
ATA_RENT_LAMPORTS = 2_039_280
TOKEN_ACCOUNT_SIZE = 165
BASE_TX_FEE = 5_000

# On-chain slippage error codes
PUMP_SLIPPAGE_ERROR_CODES: set[int] = {6002, 6003, 6042}
PUMPSWAP_SLIPPAGE_ERROR_CODES: set[int] = {6004, 6040}

# Compute budgets
PUMP_BUY_COMPUTE_UNITS = 180_000
PUMP_SELL_COMPUTE_UNITS = 120_000
# A non-SOL quote moves through Token-2022 transfers and may need its token
# account created, which costs several times what a SOL trade does.
PUMP_NON_SOL_TRADE_COMPUTE_UNITS = 400_000
PUMPSWAP_BUY_COMPUTE_UNITS = 400_000
PUMPSWAP_SELL_COMPUTE_UNITS = 300_000
PUMPSWAP_PRIORITY_FEE = 10_000
LAUNCH_COMPUTE_UNITS = 400_000

# A v1 transaction states its budget in the message header. The loaded-accounts
# limit must be set explicitly: left unset it is zero rather than the network
# default, and the transaction is rejected.
TX_V1_LOADED_ACCOUNTS_DATA_LIMIT = 64 * 1024 * 1024
