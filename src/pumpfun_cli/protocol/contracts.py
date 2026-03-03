"""Pump.fun program IDs, system addresses, and constants."""

from solders.pubkey import Pubkey

# Solana constants
LAMPORTS_PER_SOL = 1_000_000_000
TOKEN_DECIMALS = 6  # pump.fun tokens are 6 decimals (not Solana's usual 9)

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
PUMP_FEE = Pubkey.from_string("CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM")
PUMP_MAYHEM_FEE = Pubkey.from_string("GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS")
PUMP_FEE_PROGRAM = Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")
PUMP_MINT_AUTHORITY = Pubkey.from_string("TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM")

# Mayhem mode addresses
MAYHEM_PROGRAM_ID = Pubkey.from_string("MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e")
MAYHEM_GLOBAL_PARAMS = Pubkey.from_string("13ec7XdrjF3h3YcqBTFDSReRcUFwbCnJaAQspM4j6DDJ")
MAYHEM_SOL_VAULT = Pubkey.from_string("BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s")

# PumpSwap AMM addresses
PUMP_AMM_PROGRAM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
PUMP_SWAP_GLOBAL_CONFIG = Pubkey.from_string("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw")
PUMP_SWAP_EVENT_AUTHORITY = Pubkey.from_string("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR")
STANDARD_PUMPSWAP_FEE_RECIPIENT = Pubkey.from_string(
    "7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ"
)
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")

# PumpSwap instruction discriminators
PUMPSWAP_BUY_DISCRIMINATOR = bytes.fromhex("66063d1201daebea")
PUMPSWAP_SELL_DISCRIMINATOR = bytes.fromhex("33e685a4017f83ad")

# buy_exact_sol_in / buy_exact_quote_in discriminators
BUY_EXACT_SOL_IN_DISCRIMINATOR = bytes([56, 252, 116, 8, 158, 223, 205, 95])
PUMPSWAP_BUY_EXACT_QUOTE_IN_DISCRIMINATOR = bytes([198, 46, 21, 82, 180, 217, 232, 112])

# Creator fee collection discriminators
COLLECT_CREATOR_FEE_DISCRIMINATOR = bytes([20, 22, 86, 123, 198, 28, 219, 132])
COLLECT_COIN_CREATOR_FEE_DISCRIMINATOR = bytes([160, 57, 89, 42, 181, 139, 43, 66])

# PumpSwap pool data offsets
POOL_BASE_MINT_OFFSET = 43
POOL_MAYHEM_MODE_OFFSET = 243
POOL_MAYHEM_MODE_MIN_SIZE = 244
GLOBALCONFIG_RESERVED_FEE_OFFSET = 72
GLOBALCONFIG_PROTOCOL_FEE_RECIPIENT_OFFSET = 281

# Solana rent / fee constants
SOL_RENT_EXEMPT_MIN = 890_880
ATA_RENT_LAMPORTS = 2_039_280
BASE_TX_FEE = 5_000

# PumpSwap compute budgets
PUMPSWAP_BUY_COMPUTE_UNITS = 400_000
PUMPSWAP_SELL_COMPUTE_UNITS = 300_000
PUMPSWAP_PRIORITY_FEE = 10_000
