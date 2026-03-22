# Embiggenator

![Version 1.2.0](https://img.shields.io/badge/version-1.2.0-blue)
![Python >= 3.10](https://img.shields.io/badge/python-%3E%3D3.10-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

LDAP and Mattermost test data generator. Creates realistic test environments with hundreds or thousands of users, groups, teams, channels, conversations, group messages, pinned posts, and custom statuses -- all from a single config file.

Built for the [`rroemhild/docker-test-openldap`](https://github.com/rroemhild/docker-test-openldap) Docker image.

## Quick Start

1. **Create a Mattermost Personal Access Token** in your Mattermost instance (System Console or user menu). This is needed for content generation.

2. **Clone and install:**

   ```bash
   git clone https://github.com/ewwollesen/mattermost-embiggenator.git && cd mattermost-embiggenator
   python -m venv .venv && source .venv/bin/activate
   pip install .
   ```

3. **Grab the example config:**

   ```bash
   cp examples/embiggenator.yaml embiggenator.yaml
   ```

4. **Run it:**

   ```bash
   embiggenator run-all -c embiggenator.yaml \
     --host <ldap-host> --port <ldap-port> \
     --mattermost-url http://<mattermost-host>:8065 \
     --pat "$MM_PAT"
   ```

> **Note:** The default password for all generated users is `password`.

## Documentation

| Guide | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Task-oriented guide ("I want to...") and recommended Mattermost LDAP settings |
| [Command Reference](docs/commands.md) | All commands and their options |
| [Configuration](docs/configuration.md) | YAML config format, priority order, env var expansion |
| [ABAC Attributes](docs/abac.md) | Custom LDAP attributes for access control testing |
| [Docker Compose](docs/docker-compose.md) | Volume mount and sidecar deployment examples |
| [FAQ](docs/faq.md) | Troubleshooting, verification, objectClass notes |

## Disclaimer

Embiggenator is designed for local development and testing. Do not use it against production systems or on shared infrastructure where CLI arguments may be visible to other users. Sensitive values like `--pat` and `--bind-password` can be placed in a [YAML config file](docs/configuration.md) with restricted file permissions instead of passed on the command line.

## Acknowledgments

- [Robin Roemhild](https://github.com/rroemhild) for the [`docker-test-openldap`](https://github.com/rroemhild/docker-test-openldap) image that Embiggenator is built around
- Jane Austen, Emily Brontë, and Mary Shelley, for the post and attachment content
