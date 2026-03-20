# Command Reference

Flat reference for all Embiggenator commands. For task-oriented walkthroughs, see [getting-started.md](getting-started.md).

## Contents

- [`generate-ldif`](#generate-ldif)
- [`populate`](#populate)
- [`content`](#content)
- [`run-all`](#run-all)
- [`reset`](#reset)
- [`disable-user`](#disable-user)
- [`update-user`](#update-user)
- [`show-config`](#show-config)

## `generate-ldif`

Generates LDIF files to a directory for mounting into the OpenLDAP container.

```
embiggenator generate-ldif [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `-u`, `--users` | Number of users to generate | 100 |
| `-g`, `--groups` | Number of groups to generate | 10 |
| `-m`, `--members-per-group` | Members per group (integer or `min-max` range) | 5-20 |
| `-o`, `--output` | Output directory | `./embiggenator-data` |
| `-c`, `--config` | YAML config file | -- |
| `--base-dn` | Base DN | `dc=planetexpress,dc=com` |
| `--email-domain` | Email domain for generated users | `planetexpress.com` |
| `--default-password` | Password for all generated users | `password` |
| `--password-scheme` | `{SSHA}`, `{SHA}`, or `{PLAIN}` | `{SSHA}` |
| `--seed` | Random seed for reproducible output | -- |
| `--abac` | Inline ABAC attributes (see [abac.md](abac.md)) | -- |
| `--abac-profile` | ABAC profile YAML file | -- |
| `--no-defaults` | Skip bundled default LDIF files | false |

## `populate`

Connects to a running LDAP server and adds entries directly. Accepts all the same generation options as `generate-ldif`, plus:

```
embiggenator populate [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `--host` | LDAP server host | `localhost` |
| `--port` | LDAP server port | `10389` |
| `--bind-dn` | Bind DN for authentication | `cn=admin,dc=planetexpress,dc=com` |
| `--bind-password` | Bind password | `GoodNewsEveryone` |
| `--use-ssl` | Use SSL/TLS connection | false |
| `--mattermost-url` | Mattermost URL -- logs in each user to activate accounts | -- |
| `--nologin` | Skip the Mattermost login step | false |

## `content`

Generates Mattermost content against a running server. Requires users to already be logged in (via `populate --mattermost-url` or `run-all`).

```
embiggenator content [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `-c`, `--config` | YAML config file | -- |
| `--pat` | Mattermost Personal Access Token | -- |
| `--mattermost-url` | Mattermost server URL (overrides config) | `http://localhost:8065` |
| `--seed` | Random seed for reproducible output | -- |

## `run-all`

Runs everything in sequence: populate LDAP, login users to Mattermost, generate content.

```
embiggenator run-all [OPTIONS]
```

Accepts all options from `populate` plus `--pat` for content generation. If `--pat` is not provided, content generation is skipped.

## `reset`

Deletes all entries under `ou=people` and restores the 7 built-in users and 2 built-in groups from the upstream Docker image.

```
embiggenator reset [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `--host` | LDAP server host | `localhost` |
| `--port` | LDAP server port | `10389` |
| `--bind-dn` | Bind DN for authentication | `cn=admin,dc=planetexpress,dc=com` |
| `--bind-password` | Bind password | `GoodNewsEveryone` |
| `--use-ssl` | Use SSL/TLS connection | false |
| `--base-dn` | Base DN | `dc=planetexpress,dc=com` |
| `--no-restore` | Don't restore built-in defaults after clearing | false |
| `--mattermost-url` | Mattermost URL -- also delete all non-admin users from Mattermost | -- |
| `--pat` | Mattermost Personal Access Token (required with `--mattermost-url`) | -- |
| `--yes` | Skip confirmation prompt | false |

## `disable-user`

Marks one or more LDAP users as disabled by setting `description=DISABLED`.

```
embiggenator disable-user USERNAME [USERNAME ...]
```

| Option | Description | Default |
|---|---|---|
| `--host` | LDAP server host | `localhost` |
| `--port` | LDAP server port | `10389` |
| `--bind-dn` | Bind DN for authentication | `cn=admin,dc=planetexpress,dc=com` |
| `--bind-password` | Bind password | `GoodNewsEveryone` |
| `--use-ssl` | Use SSL/TLS connection | false |
| `--base-dn` | Base DN | `dc=planetexpress,dc=com` |

## `update-user`

Modifies LDAP attributes for an existing user.

```
embiggenator update-user USERNAME [OPTIONS]
```

| Option | Description | Default |
|---|---|---|
| `--set` | Attribute to set (`ATTR=VALUE`, repeatable) | (required) |
| `--host` | LDAP server host | `localhost` |
| `--port` | LDAP server port | `10389` |
| `--bind-dn` | Bind DN for authentication | `cn=admin,dc=planetexpress,dc=com` |
| `--bind-password` | Bind password | `GoodNewsEveryone` |
| `--use-ssl` | Use SSL/TLS connection | false |
| `--base-dn` | Base DN | `dc=planetexpress,dc=com` |

## `show-config`

Displays the resolved configuration after merging defaults, YAML file, and CLI options.

```
embiggenator show-config [-c CONFIG]
```
