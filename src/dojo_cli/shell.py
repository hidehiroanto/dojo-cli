"""Handles custom shell initialization."""

import shlex

from .remote import run_cmd


def init_bash(command_string: str | None = None):
    bash_args = ['bash', '-l']
    if command_string is not None:
        bash_args += ['-c', command_string]
    run_cmd(shlex.join(bash_args))

def init_fish(command: str | None = None, init_command: str | None = None):
    fish_args = ['fish', '-l']
    if command is not None:
        fish_args += ['-c', command]
    if init_command is not None:
        fish_args += ['-C', init_command]
    run_cmd(shlex.join(fish_args))

def init_nu(commands: str | None = None, exec_commands: str | None = None):
    nu_args = ['nu', '-l']
    if commands is not None:
        nu_args += ['-c', commands]
    if exec_commands is not None:
        nu_args += ['-e', exec_commands]
    run_cmd(shlex.join(nu_args))

def init_zsh(command: str | None = None):
    zsh_args = ['zsh', '-l']
    if command is not None:
        zsh_args += ['-c', command]
    run_cmd(shlex.join(zsh_args))
