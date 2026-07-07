"""
hoyo-assistant: A tool for automating HoYoLAB/MiYouShe daily tasks.
"""

from importlib.metadata import version

from .runner import run_multi_account, run_single_account

__version__ = version("hoyo-assistant")
__all__ = ["run_multi_account", "run_single_account"]
