# Embiggenator

LDAP test data generator for Mattermost. Generates hundreds or thousands of realistic LDAP user and group entries for testing LDAP connections, group sync, and ABAC against the [`rroemhild/docker-test-openldap`](https://github.com/rroemhild/docker-test-openldap) Docker image.

The upstream image only ships 7 users and 2 groups. Embiggenator fixes that.

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
users: 500
groups: 20
members_per_group: 10-50
email_domain: planetexpress.com
default_password: password
password_scheme: "{SSHA}"
seed: 42

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
```

Use it with:

```bash
embiggenator generate-ldif -c embiggenator.yaml -o ./embiggenator-data
```

CLI flags override values from the config file:

```bash
# Uses 50 users instead of the 500 in the YAML, keeps everything else
embiggenator generate-ldif -c embiggenator.yaml -u 50 -o ./embiggenator-data
```

## ABAC Attributes

Custom attributes are assigned to generated users using standard `inetOrgPerson` attributes, so no LDAP schema changes are needed.

### Via YAML config

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

### Via inline flag

```bash
embiggenator generate-ldif -u 100 --abac "departmentNumber=Engineering,Sales,Support;businessCategory=Public,Confidential,Secret"
```

Multiple attributes are separated by `;`, values within an attribute by `,`.

### Via profile file

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
  "(objectClass=groupOfNames)" cn
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
