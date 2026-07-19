"""
Configuration & Namespace Import Loader Module for UNIFIED ASSISTANT.
Resolves and loads modules from independent sender/ and reader/ packages without shadowing.
Uses a Call-Stack Config Proxy to dynamically route 'config' module lookups.
"""

import sys
from pathlib import Path
import importlib
from typing import Any

# Resolve base directories
ASSISTANT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ASSISTANT_DIR.parent
SENDER_DIR = PROJECT_ROOT / "sender"
READER_DIR = PROJECT_ROOT / "reader"

# 1. Load SENDER config module in isolation
sys.modules.pop("config", None)
original_path = list(sys.path)
sys.path.insert(0, str(SENDER_DIR))
try:
    sender_config_mod = importlib.import_module("config")
    SENDER_CONFIG = sender_config_mod.Config
finally:
    sys.path = original_path
    sys.modules.pop("config", None)

# 2. Load READER config module in isolation
sys.modules.pop("config", None)
sys.path.insert(0, str(READER_DIR))
try:
    reader_config_mod = importlib.import_module("config")
    READER_CONFIG = reader_config_mod.Config
finally:
    sys.path = original_path
    sys.modules.pop("config", None)


# 3. Define the Call-Stack Config Proxy to resolve namespace collisions transparently
class ConfigProxyModule:
    """Proxy module in sys.modules['config'] that delegates lookups based on calling frame path."""
    
    def __getattr__(self, name: str) -> Any:
        # Walk up the call stack to see where the call is coming from
        frame = sys._getframe(1)
        while frame:
            filename = frame.f_code.co_filename
            if "reader" in filename:
                return getattr(reader_config_mod, name)
            elif "sender" in filename:
                return getattr(sender_config_mod, name)
            frame = frame.f_back
            
        # Fallback to sender config
        return getattr(sender_config_mod, name)

    def __dir__(self) -> list[str]:
        return ["Config", "BASE_DIR"]


# Set the proxy in sys.modules to satisfy "from config import Config" dynamically
sys.modules["config"] = ConfigProxyModule()  # type: ignore


# 4. Helper modules for routing dynamic imports
def import_sender_module(module_name: str) -> Any:
    """
    Dynamically imports a module from the sender package.
    Isolates the 'tools' namespace to prevent conflicts with the reader package.
    """
    cached_tools = sys.modules.pop("tools", None)
    
    original_path = list(sys.path)
    sys.path.insert(0, str(SENDER_DIR))
    
    try:
        module = importlib.import_module(module_name)
    finally:
        sys.path = original_path
        sys.modules.pop("tools", None)
        if cached_tools:
            sys.modules["tools"] = cached_tools
            
    return module


def import_reader_module(module_name: str) -> Any:
    """
    Dynamically imports a module from the reader package.
    Isolates the 'tools' namespace to prevent conflicts with the sender package.
    """
    cached_tools = sys.modules.pop("tools", None)
    
    original_path = list(sys.path)
    sys.path.insert(0, str(READER_DIR))
    
    try:
        module = importlib.import_module(module_name)
    finally:
        sys.path = original_path
        sys.modules.pop("tools", None)
        if cached_tools:
            sys.modules["tools"] = cached_tools
            
    return module
