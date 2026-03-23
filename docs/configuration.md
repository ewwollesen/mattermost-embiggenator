# Configuration

Options are resolved in priority order: **defaults < YAML config file < CLI flags**.

## Contents

- [YAML Config File](#yaml-config-file)
- [Auth Method](#auth-method)
- [Environment Variable Expansion](#environment-variable-expansion)
- [Channel Distribution](#channel-distribution)
- [Password Options](#password-options)
- [Profile Pictures](#profile-pictures)

## YAML Config File

```yaml
# auth_method: email  # "ldap" (default) or "email" (email/password, no LDAP needed)

# LDAP settings (ignored when auth_method is "email")
users: 500
groups: 20
members_per_group: 10-50
email_domain: planetexpress.com
default_password: password
password_scheme: "{SSHA}"
seed: 42
avatar_probability: 0.8             # fraction of users that get a jpegPhoto avatar

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
  attachment_probability: 0.1        # fraction of posts that get a file attachment
  attachment_size: 1024-5242880      # attachment size range in bytes (1 KB - 5 MB)
  direct_messages: 10-30
  dms_per_conversation: 3-10
  group_messages: 5-15               # number of group message conversations (3+ users)
  group_message_members: 3-7         # members per group message
  group_messages_per_conversation: 5-15
  pin_probability: 0.05              # fraction of posts to pin to their channel
  status_probability: 0.6            # fraction of users that get a custom status

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

## Auth Method

By default, Embiggenator creates users via LDAP (`auth_method: ldap`). If you don't have an LDAP server or want email/password accounts instead, use `auth_method: email`:

```yaml
auth_method: email
```

Or via CLI flag:

```bash
embiggenator run-all -c embiggenator.yaml --auth-method email --pat "$MM_PAT"
```

In email mode:
- Users are created directly on Mattermost via `POST /api/v4/users` (email/password accounts)
- A Mattermost PAT with system admin permissions is **required**
- LDAP-specific features (groups, ABAC attributes, avatars, `password_scheme`) are skipped
- The `users`, `email_domain`, and `default_password` settings work the same way
- Content generation works identically once users are created

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

## Profile Pictures

Set `avatar_probability` to generate `jpegPhoto` attributes on LDAP users. Mattermost syncs these as profile pictures when `PictureAttribute` is set to `jpegPhoto` in LDAP settings (see [recommended settings](getting-started.md#recommended-mattermost-ldap-settings)).

```yaml
avatar_probability: 0.8   # 80% of users get a profile picture
```

The images are minimal solid-color 8x8 JPEGs (16 colors). They're small by design — they exist to test the LDAP photo sync pipeline, not to look realistic. The color assigned to each user is deterministic when using `seed`.
