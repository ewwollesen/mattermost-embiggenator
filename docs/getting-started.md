# Getting Started

Task-oriented guide for common Embiggenator workflows. For the full option reference, see [commands.md](commands.md).

## Contents

- [I want to set up a full test environment](#i-want-to-set-up-a-full-test-environment)
- [I only need LDAP users (no Mattermost)](#i-only-need-ldap-users-no-mattermost)
- [I want to generate Mattermost content for existing users](#i-want-to-generate-mattermost-content-for-existing-users)
- [I need to start over / reset everything](#i-need-to-start-over--reset-everything)
- [I need to modify existing users](#i-need-to-modify-existing-users)
- [Recommended Mattermost LDAP Settings](#recommended-mattermost-ldap-settings)
- [Reproducible Output](#reproducible-output)

## I want to set up a full test environment

Use `run-all` to populate LDAP, log users into Mattermost, and generate content in one shot:

```bash
embiggenator run-all -c embiggenator.yaml \
  --host localhost --port 10389 \
  --mattermost-url http://localhost:8065 \
  --pat "$MM_PAT"
```

This:
1. Adds generated users and groups to your LDAP server (with optional profile pictures via `jpegPhoto`)
2. Logs each user into Mattermost (creating their accounts)
3. Creates teams, channels, posts, threads, reactions, DMs, group messages, pinned posts, and custom user statuses

If `--pat` is not provided, content generation is skipped (steps 1-2 only).

> **Note:** The default password for all generated users is `password`. See [configuration.md](configuration.md) for how to change it.

## I only need LDAP users (no Mattermost)

### Option A: Generate LDIF files for Docker volume mount

```bash
embiggenator generate-ldif -u 500 -g 20 -m 10-50 -o ./embiggenator-data
```

This produces a directory containing:
- The 10 built-in LDIF files from the upstream OpenLDAP image (prefixed `00_`, `10_`, `30_`)
- `50_a_users.ldif` -- generated users
- `50_b_groups.ldif` -- generated groups

Mount the output directory into your OpenLDAP container. See [docker-compose.md](docker-compose.md) for examples.

### Option B: Populate a running LDAP server directly

```bash
embiggenator populate -u 500 -g 20 -m 10-50 --host localhost --port 10389
```

Existing entries are skipped automatically.

## I want to generate Mattermost content for existing users

If users are already logged into Mattermost (via `populate --mattermost-url` or `run-all`), generate content separately:

```bash
embiggenator content -c embiggenator.yaml --pat "$MM_PAT"
```

## I need to start over / reset everything

```bash
# Wipe LDAP entries and restore built-in defaults (prompts for confirmation)
embiggenator reset --host localhost --port 10389

# Skip the confirmation prompt
embiggenator reset --host localhost --port 10389 --yes

# Also wipe Mattermost users and teams
embiggenator reset --host localhost --port 10389 \
  --mattermost-url http://localhost:8065 --pat "$MM_PAT" --yes
```

The Mattermost reset permanently deletes all non-bot, non-admin users and all teams, then creates a "Default" team so the server remains usable. Requires `ServiceSettings.EnableAPIUserDeletion=true` and `EnableAPITeamDeletion=true` on the Mattermost server.

## I need to modify existing users

### Disable a user

```bash
embiggenator disable-user jdoe

# Multiple users at once
embiggenator disable-user jdoe asmith bwilson
```

Sets `description=DISABLED` on the LDAP entry. Mattermost will deactivate these users on next LDAP sync if the user filter excludes disabled users (see recommended settings below).

### Update user attributes

```bash
# Change a user's last name
embiggenator update-user jdoe --set sn=NewLastName

# Update multiple attributes at once
embiggenator update-user jdoe --set sn=Smith --set mail=jsmith@example.com

# Change an ABAC attribute
embiggenator update-user jdoe --set businessCategory=Secret
```

## Recommended Mattermost LDAP Settings

These settings work with the default Embiggenator configuration and the `rroemhild/docker-test-openldap` image. Apply them in your Mattermost `config.json` or via the System Console:

```json
{
  "LdapSettings": {
    "Enable": true,
    "EnableSync": true,
    "LdapServer": "openldap",
    "LdapPort": 10389,
    "BaseDN": "dc=planetexpress,dc=com",
    "BindUsername": "cn=admin,dc=planetexpress,dc=com",
    "BindPassword": "GoodNewsEveryone",
    "UserFilter": "(&(objectClass=inetOrgPerson)(!(description=DISABLED)))",
    "GroupFilter": "(objectClass=groupOfNames)",
    "GroupDisplayNameAttribute": "cn",
    "GroupIdAttribute": "cn",
    "FirstNameAttribute": "givenName",
    "LastNameAttribute": "sn",
    "EmailAttribute": "mail",
    "UsernameAttribute": "uid",
    "NicknameAttribute": "givenName",
    "IdAttribute": "entryUUID",
    "PositionAttribute": "ou",
    "LoginIdAttribute": "uid",
    "PictureAttribute": "jpegPhoto"
  }
}
```

Key points:
- **UserFilter** excludes users with `description=DISABLED`, so `disable-user` works with LDAP sync
- **GroupFilter** uses `groupOfNames` -- the objectClass used by `populate` and `run-all`. If you use `generate-ldif` instead, change this to `(objectClass=Group)` to match the upstream image defaults. See [FAQ](faq.md#objectclass-notes) for details.
- **IdAttribute** is `entryUUID`, which is stable across attribute changes

## Reproducible Output

Use `--seed` to get deterministic output:

```bash
embiggenator generate-ldif -u 100 -g 10 --seed 42 -o ./data1
embiggenator generate-ldif -u 100 -g 10 --seed 42 -o ./data2
# data1/ and data2/ will contain identical entries
```

This applies to all commands -- LDAP generation, content generation, channel names, member assignments, and post content are all deterministic for a given seed. Set it in your YAML config to make it permanent:

```yaml
seed: 42
```
