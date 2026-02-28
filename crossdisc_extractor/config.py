from enum import Enum

class LanguageMode(str, Enum):
    CHINESE = "chinese"
    ORIGINAL = "original"

# Global configuration object
class Config:
    LANGUAGE_MODE: LanguageMode = LanguageMode.CHINESE

_config = Config()

def set_language_mode(mode: str):
    _config.LANGUAGE_MODE = LanguageMode(mode)

def get_language_mode() -> LanguageMode:
    return _config.LANGUAGE_MODE
