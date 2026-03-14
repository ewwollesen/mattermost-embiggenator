# Embiggenator

LDAP and Mattermost test data generator. Creates realistic test environments with hundreds or thousands of users, groups, teams, channels, and conversations — all from a single config file.

Built for the [`rroemhild/docker-test-openldap`](https://github.com/rroemhild/docker-test-openldap) Docker image (which only ships 7 users and 2 groups). Embiggenator fixes that.

## Features

- Creates a configurable number of LDAP users and groups with realistic names
- Assigns a random subset of users to each group
- Adds custom LDAP attributes for ABAC policy testing
- Logs in newly created LDAP users to Mattermost so they appear in the instance
- Creates Mattermost teams and adds users to them
- Creates a configurable number of public and private channels
- Populates channels with posts using passages from Pride and Prejudice and Wuthering Heights
- Generates threaded replies and emoji reactions on posts
- Creates direct message conversations between random user pairs
- Supports deterministic, reproducible output via `--seed`
- Driven entirely by a single YAML config file, with CLI overrides

## Installation

```bash
pip install .
```

Or in development mode:

```bash
pip install -e .
```

Requires Python 3.10+.

## Quick Start

### 1. Generate LDIF files and mount into Docker Compose

```bash
# Generate 500 users and 20 groups, with 10-50 members per group
embiggenator generate-ldif -u 500 -g 20 -m 10-50 -o ./embiggenator-data
```

This produces a directory containing:
- The 10 built-in LDIF files from the upstream OpenLDAP image (prefixed `00_`, `10_`, `30_`)
- `50_a_users.ldif` -- generated users
- `50_b_groups.ldif` -- generated groups

The `50_` prefix ensures generated data loads after the built-in defaults.

Add the volume mount to your `docker-compose.yml`:

```yaml
services:
  openldap:
    image: ghcr.io/rroemhild/docker-test-openldap:master
    ports:
      - "10389:10389"
      - "10636:10636"
    volumes:
      - ./embiggenator-data:/opt/openldap/bootstrap/data:ro
```

Then start it:

```bash
docker compose up -d
```

### 2. Populate a running LDAP server directly

If you already have a running OpenLDAP container, you can inject entries directly:

```bash
embiggenator populate -u 500 -g 20 -m 10-50 --host localhost --port 10389
```

Existing entries are skipped automatically.

To also create Mattermost user accounts (by logging each user in via the API), add `--mattermost-url`:

```bash
embiggenator populate -u 500 -g 20 -m 10-50 \
  --host localhost --port 10389 \
  --mattermost-url http://localhost:8065
```

Mattermost only creates LDAP user accounts on first login, so this step triggers that for every generated user. Use `--nologin` to skip it if you only need the LDAP entries.

> **Mattermost note:** When using `populate` or `reset`, groups are created with `objectClass=groupOfNames` (the standard OpenLDAP objectClass). You must set your Mattermost group filter accordingly:
>
> `LdapSettings.GroupFilter` = `(objectClass=groupOfNames)`
>
> The `generate-ldif` mode uses the AD-style `objectClass=Group` to match the upstream docker-test-openldap defaults, so if you use that mode you can keep `(objectClass=Group)` as the filter.

### 3. Generate Mattermost content

Once users are logged in, generate teams, channels, posts, threads, reactions, and DMs:

```bash
embiggenator content -c embiggenator.yaml --pat "$MM_PAT"
```

Or do everything in one shot with `run-all`:

```bash
embiggenator run-all -c embiggenator.yaml \
  --host localhost --port 10389 \
  --mattermost-url http://localhost:8065 \
  --pat "$MM_PAT"
```

This populates LDAP, logs users into Mattermost, and generates all content in sequence.

## Commands

### `generate-ldif`

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
| `--abac` | Inline ABAC attributes (see below) | -- |
| `--abac-profile` | ABAC profile YAML file | -- |
| `--no-defaults` | Skip bundled default LDIF files | false |

### `populate`

Connects to a running LDAP server and adds entries directly.

```
embiggenator populate [OPTIONS]
```

Accepts all the same generation options as `generate-ldif`, plus:

| Option | Description | Default |
|---|---|---|
| `--host` | LDAP server host | `localhost` |
| `--port` | LDAP server port | `10389` |
| `--bind-dn` | Bind DN for authentication | `cn=admin,dc=planetexpress,dc=com` |
| `--bind-password` | Bind password | `GoodNewsEveryone` |
| `--use-ssl` | Use SSL/TLS connection | false |
| `--mattermost-url` | Mattermost URL — logs in each user to activate accounts | -- |
| `--nologin` | Skip the Mattermost login step | false |

### `content`

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

### `run-all`

Runs everything in sequence: populate LDAP, login users to Mattermost, generate content.

```
embiggenator run-all [OPTIONS]
```

Accepts all options from `populate` plus `--pat` for content generation. If `--pat` is not provided, content generation is skipped.

### `reset`

Connects to a running LDAP server, deletes all entries under `ou=people`, and restores the 7 built-in users and 2 built-in groups from the upstream Docker image. Useful when you've run `populate` multiple times or otherwise need a clean slate.

```bash
# Wipe everything and restore built-in defaults (prompts for confirmation)
embiggenator reset --host localhost --port 10389

# Skip the confirmation prompt
embiggenator reset --host localhost --port 10389 --yes

# Wipe everything, don't restore defaults (empty OU)
embiggenator reset --host localhost --port 10389 --no-restore --yes
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
| `--yes` | Skip confirmation prompt | false |

### `show-config`

Displays the resolved configuration after merging defaults, YAML file, and CLI options. Useful for debugging.

```bash
embiggenator show-config
embiggenator show-config -c embiggenator.yaml
```

## Configuration

Options are resolved in priority order: **defaults < YAML config file < CLI flags**.

### YAML Config File

```yaml
# LDAP settings
users: 500
groups: 20
members_per_group: 10-50
email_domain: planetexpress.com
default_password: password
password_scheme: "{SSHA}"
seed: 42

# ABAC attributes for custom LDAP attribute testing
abac:
  attributes:
    - name: departmentNumber
      values: ["Engineering", "Sales", "Support", "Marketing", "Finance"]
    - name: businessCategory
      values: ["Public", "Confidential", "Secret"]
      weights: [50, 30, 20]
    - name: employeeType
      values: ["Full-Time", "Part-Time", "Contractor", "Intern"]
      weights: [60, 15, 15, 10]

# Mattermost connection
mattermost:
  url: http://localhost:8065
  pat: "${MM_PAT}"              # env var expansion supported

# Content generation
content:
  # Option A: total channels distributed across teams
  channels: 100-200

  # Option B: channels per team (used if 'channels' is not set)
  # channels_per_team: 5-10

  private_channel_probability: 0.2
  members_per_channel: 5-50
  posts_per_channel: 20-50
  reply_probability: 0.3
  replies_per_thread: 1-5
  reaction_probability: 0.2
  reactions_per_post: 1-3
  direct_messages: 10-30
  dms_per_conversation: 3-10

  teams:
    - name: engineering
      display_name: Engineering
      channels:                     # explicit channels (auto-generated ones fill the rest)
        - name: general
        - name: backend
          type: private
        - name: frontend
    - name: support
      display_name: Support
      channels_per_team: 20-30      # per-team override
```

Use it with:

```bash
embiggenator run-all -c embiggenator.yaml \
  --host localhost --port 10389 \
  --pat "$MM_PAT"
```

CLI flags override values from the config file:

```bash
# Uses 50 users instead of the 500 in the YAML, keeps everything else
embiggenator generate-ldif -c embiggenator.yaml -u 50 -o ./embiggenator-data
```

## ABAC Attributes

Every generated user gets custom LDAP attributes assigned by default, using standard `inetOrgPerson` attributes (no schema changes needed):

| Attribute | Values | Distribution |
|---|---|---|
| `businessCategory` | `IL4`, `IL5`, `IL6` | Weighted (50/35/15) |
| `departmentNumber` | `Engineering`, `Sales`, `Support`, `Finance`, `HR` | Uniform |
| `employeeType` | `Full-Time`, `Contractor`, `Intern` | Weighted (70/20/10) |

These are useful for testing ABAC policies out of the box — the values are predictable and easy to find in the Mattermost UI or server logs.

### Custom ABAC attributes

Specifying any custom ABAC attributes (via `--abac`, `--abac-profile`, or YAML config) replaces the defaults entirely.

#### Via YAML config

```yaml
abac:
  attributes:
    - name: departmentNumber
      values: ["Engineering", "Sales", "Support"]
    - name: businessCategory
      values: ["Public", "Confidential", "Secret"]
      weights: [50, 30, 20]
```

When `weights` are provided, values are selected according to those proportions. Without weights, values are distributed uniformly.

#### Via inline flag

```bash
embiggenator generate-ldif -u 100 --abac "departmentNumber=Engineering,Sales,Support;businessCategory=Public,Confidential,Secret"
```

Multiple attributes are separated by `;`, values within an attribute by `,`.

#### Via profile file

```bash
embiggenator generate-ldif -u 100 --abac-profile abac-attrs.yaml
```

Where `abac-attrs.yaml` follows the same format as the `abac:` section in the main config.

## Reproducible Output

Use `--seed` to get deterministic output:

```bash
embiggenator generate-ldif -u 100 -g 10 --seed 42 -o ./data1
embiggenator generate-ldif -u 100 -g 10 --seed 42 -o ./data2
# data1/ and data2/ will contain identical entries
```

This applies to all commands — LDAP generation, content generation, channel names, member assignments, and post content are all deterministic for a given seed.

## Docker Compose Examples

### Volume mount (recommended)

Generate LDIF files first, then mount them into the container:

```yaml
services:
  openldap:
    image: ghcr.io/rroemhild/docker-test-openldap:master
    ports:
      - "10389:10389"
      - "10636:10636"
    volumes:
      - ./embiggenator-data:/opt/openldap/bootstrap/data:ro
```

### Sidecar container

Build and run embiggenator as a sidecar that populates the LDAP server on startup:

```yaml
services:
  openldap:
    image: ghcr.io/rroemhild/docker-test-openldap:master
    ports:
      - "10389:10389"
      - "10636:10636"

  embiggenator:
    build: .
    depends_on:
      - openldap
    command: >
      populate
        --host openldap
        --port 10389
        -u 500
        -g 20
        -m 10-50
```

Working examples are in the [`examples/`](examples/) directory.

## Verification

After starting the container, verify entries were loaded:

```bash
# Count all users (built-in + generated)
ldapsearch -H ldap://localhost:10389 \
  -D "cn=admin,dc=planetexpress,dc=com" \
  -w GoodNewsEveryone \
  -b "ou=people,dc=planetexpress,dc=com" \
  "(uid=*)" uid | grep numEntries

# List generated groups
ldapsearch -H ldap://localhost:10389 \
  -D "cn=admin,dc=planetexpress,dc=com" \
  -w GoodNewsEveryone \
  -b "ou=people,dc=planetexpress,dc=com" \
  "(objectClass=Group)" cn
```

With 50 generated users, you should see 57 total user entries (7 built-in + 50 generated).

## Running as a Python module

```bash
python -m embiggenator generate-ldif -u 50 -o ./data
```

## Running Tests

```bash
pip install pytest
pytest
```
