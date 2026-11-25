"""
hoyo-assistant: A tool for automating HoYoLAB/MiYouShe daily tasks.
"""

from importlib.metadata import version

from .runner import run_account, run_accounts

__version__ = version("hoyo-assistant")
__all__ = ["run_account", "run_accounts"]
