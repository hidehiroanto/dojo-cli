# Dojo CLI

`dojo-cli` is a Python package to interact with the pwn.college API and website.
It comes with a command line interface called `dojo`.

## Images

![dojo](https://github.com/hidehiroanto/dojo-cli/blob/main/images/help-black.png)
![trogon](https://github.com/hidehiroanto/dojo-cli/blob/main/images/trogon-tokyo-night.png)
![tree](https://github.com/hidehiroanto/dojo-cli/blob/main/images/tree-catppuccin-mocha.png)
![sensai](https://github.com/hidehiroanto/dojo-cli/blob/main/images/sensai-gruvbox.png)
![fastfetch](https://github.com/hidehiroanto/dojo-cli/blob/main/images/nu-fastfetch.png)

## Quickstart

The easiest way to get started is with `uv`.

If you don't have `uv` yet, follow the installation instructions [here](https://docs.astral.sh/uv/getting-started/installation/).

Then run this command to install and launch the CLI:
```sh
uvx --from git+https://github.com/hidehiroanto/dojo-cli dojo
```

If you don't want to type that out every time, install it long term with this command:
```sh
uv tool install --from git+https://github.com/hidehiroanto/dojo-cli dojo-cli
```

Then just run `dojo` to start the CLI.

If you want to add the Python package and CLI as a dependency to your project, run this:
```sh
uv add git+https://github.com/hidehiroanto/dojo-cli
```

If you want to add the Python package and CLI to your system environment, run this:
```sh
uv pip install --break-system-packages --strict --system git+https://github.com/hidehiroanto/dojo-cli
```

## Current Features

- Rich text formatting
- Logging into the API
- Generating an SSH keypair and adding the public key to your account
- Fetching user details
- Getting rankings in dojos and modules (now with images!)
- Getting information about belted users
- Listing the names and descriptions of dojos, modules, and challenges
- An interactive tree view to read challenge descriptions and start challenges
- Starting, restarting, and stopping a challenge
- Checking the status of a challenge
- Connecting to a challenge with SSH
- Running a remote command on a challenge
- Finding the largest files in your home directory
- Downloading files from and uploading files to the remote server
- Using the text editor of your choice to edit files on the remote server
- Getting a hint about the flag
- Talking with SensAI
- Submitting flags
- Custom configuration in either JSON or YAML format
- A TUI to help you navigate all this
- And more!

## Contributing

If you find a bug or want to add a feature, feel free to open an issue or a pull request.

## Thanks

Thank you especially to the following people:

- The entire [pwn.college](https://github.com/pwncollege) team for creating the [platform](https://github.com/pwncollege/dojo)
- [Zeeshan](https://github.com/Zeeshan12340) for letting me fork his [pypwncollege](https://github.com/Zeeshan12340/pypwncollege) repo
- [COMBAT](https://github.com/TheodorKitzenmaier) for the immediate inspiration
