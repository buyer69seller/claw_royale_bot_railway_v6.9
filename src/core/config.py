# src/core/config.py
"""Konfigurasi dari environment"""

import os
from dotenv import load_dotenv
from .constants import DEFAULT_ENTRY_TYPE, DEFAULT_PREFERRED_MODE, DEFAULT_ACTION_INTERVAL
from .exceptions import ConfigurationError

# Load .env
load_dotenv()

# Required
API_KEY = os.getenv("CLAW_API_KEY", "").strip()
if not API_KEY:
    raise ConfigurationError("CLAW_API_KEY is required. Please set it in .env file.")

# Optional with defaults
ENTRY_TYPE = os.getenv("ENTRY_TYPE", DEFAULT_ENTRY_TYPE).lower()
PREFERRED_MODE = os.getenv("PREFERRED_MODE", DEFAULT_PREFERRED_MODE).lower()
ACTION_INTERVAL_SECONDS = float(os.getenv("ACTION_INTERVAL_SECONDS", str(DEFAULT_ACTION_INTERVAL)))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
STRATEGY_MODE = os.getenv("STRATEGY_MODE", "hybrid").lower()

# Validate
if ENTRY_TYPE not in ["free", "paid"]:
    raise ConfigurationError(f"Invalid ENTRY_TYPE: {ENTRY_TYPE}. Must be 'free' or 'paid'")

if PREFERRED_MODE not in ["offchain", "onchain"]:
    raise ConfigurationError(f"Invalid PREFERRED_MODE: {PREFERRED_MODE}. Must be 'offchain' or 'onchain'")

if STRATEGY_MODE not in ["hybrid", "scan_clear"]:
    raise ConfigurationError(f"Invalid STRATEGY_MODE: {STRATEGY_MODE}. Must be 'hybrid' or 'scan_clear'")