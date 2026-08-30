"""Utility modules."""

from omniscribe.utils.env import (
    env_bool,
    env_int,
    env_list_csv,
    env_str,
    load_dotenv,
    update_dotenv,
)
from omniscribe.utils.file import write_atomic
from omniscribe.utils.security import check_ssrf_target_sync, is_ssrf_target
from omniscribe.utils.structured_logging import (
    DEFAULT_LOG_FORMAT,
    DEFAULT_LOG_LEVEL,
    JsonFormatter,
    configure_logging,
    is_configured,
    merge_extras,
)
from omniscribe.utils.tqdm_patch import SilentTqdm
from omniscribe.utils.tqdm_patch import apply as apply_tqdm_patch

__all__ = [
    "DEFAULT_LOG_FORMAT",
    "DEFAULT_LOG_LEVEL",
    "JsonFormatter",
    "SilentTqdm",
    "apply_tqdm_patch",
    "check_ssrf_target_sync",
    "configure_logging",
    "env_bool",
    "env_int",
    "env_list_csv",
    "env_str",
    "is_configured",
    "is_ssrf_target",
    "load_dotenv",
    "merge_extras",
    "update_dotenv",
    "write_atomic",
]
