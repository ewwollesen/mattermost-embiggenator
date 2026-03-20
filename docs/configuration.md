# Configuration

Options are resolved in priority order: **defaults < YAML config file < CLI flags**.

## YAML Config File

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

A working example config is at [`examples/embiggenator.yaml`](../examples/embiggenator.yaml).

## Environment Variable Expansion

String values in the YAML config can reference environment variables using `${VAR_NAME}` syntax:

```yaml
mattermost:
  pat: "${MM_PAT}"
```

This is especially useful for secrets like the Mattermost Personal Access Token, so they don't have to be hardcoded in the config file.

## Channel Distribution

There are two ways to control how many channels are created:

**Option A: Total channels** -- Set `content.channels` to a total count (or range) distributed across all teams:

```yaml
content:
  channels: 100-200
```

**Option B: Channels per team** -- Set `content.channels_per_team` to control each team individually:

```yaml
content:
  channels_per_team: 5-10
```

Individual teams can override with their own `channels_per_team`:

```yaml
content:
  channels_per_team: 5-10
  teams:
    - name: engineering
      channels_per_team: 20-30    # override for this team
```

If both `channels` and per-team overrides are set and the overrides exceed the total, you'll see a warning. See [FAQ](faq.md#channel-override-warning) for details.

## Password Options

| Option | Description | Default |
|---|---|---|
| `default_password` | Password assigned to all generated users | `password` |
| `password_scheme` | Hash scheme: `{SSHA}`, `{SHA}`, or `{PLAIN}` | `{SSHA}` |

Set via YAML:

```yaml
default_password: password
password_scheme: "{SSHA}"
```

Or via CLI flags:

```bash
embiggenator generate-ldif --default-password mypass --password-scheme "{SHA}"
```
