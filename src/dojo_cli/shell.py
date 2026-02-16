"""
Handles custom shell initialization.
"""

import shlex
from typing import Optional

from .remote import run_cmd

def init_bash(command_string: Optional[str] = None):
    bash_argv = ['bash', '-l']
    if command_string is not None:
        bash_argv += ['-c', command_string]
    run_cmd(shlex.join(bash_argv))

def init_fish(command: Optional[str] = None, init_command: Optional[str] = None):
    fish_argv = ['fish', '-l']
    if command is not None:
        fish_argv += ['-c', command]
    if init_command is not None:
        fish_argv += ['-C', init_command]
    run_cmd(shlex.join(fish_argv))

def init_nu(commands: Optional[str] = None, exec_commands: Optional[str] = None):
    nu_argv = ['nu', '-l']
    if commands is not None:
        nu_argv += ['-c', commands]
    if exec_commands is not None:
        nu_argv += ['-e', exec_commands]
    run_cmd(shlex.join(nu_argv))

def init_zsh(command: Optional[str] = None):
    zsh_argv = ['zsh', '-l']
    if command is not None:
        zsh_argv += ['-c', command]
    run_cmd(shlex.join(zsh_argv))
