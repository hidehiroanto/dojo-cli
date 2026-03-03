"""
Handles custom shell initialization.
"""

import shlex
from typing import Optional

from .remote import run_cmd

def init_bash(command_string: Optional[str] = None):
    bash_args = ['bash', '-l']
    if command_string is not None:
        bash_args += ['-c', command_string]
    run_cmd(shlex.join(bash_args))

def init_fish(command: Optional[str] = None, init_command: Optional[str] = None):
    fish_args = ['fish', '-l']
    if command is not None:
        fish_args += ['-c', command]
    if init_command is not None:
        fish_args += ['-C', init_command]
    run_cmd(shlex.join(fish_args))

def init_nu(commands: Optional[str] = None, exec_commands: Optional[str] = None):
    nu_args = ['nu', '-l']
    if commands is not None:
        nu_args += ['-c', commands]
    if exec_commands is not None:
        nu_args += ['-e', exec_commands]
    run_cmd(shlex.join(nu_args))

def init_zsh(command: Optional[str] = None):
    zsh_args = ['zsh', '-l']
    if command is not None:
        zsh_args += ['-c', command]
    run_cmd(shlex.join(zsh_args))
