# FAQ & Troubleshooting

## Contents

- [Channel Override Warning](#channel-override-warning)
- [objectClass Notes](#objectclass-notes)
- [Verification](#verification)
- [Running as a Python Module](#running-as-a-python-module)
- [Running Tests](#running-tests)

## Channel Override Warning

> "Warning: per-team channel overrides (X) exceed total channels target (Y). Override totals will be kept."

Your config has a top-level `channels` target (distributed across all teams) **and** individual teams with `channels_per_team` overrides. The per-team overrides already add up to more than the total target, so the total is effectively ignored.

To fix it, either:
- Increase `channels` to at least match the sum of your per-team overrides
- Remove the top-level `channels` setting and let per-team values control everything
- Lower the per-team overrides

## objectClass Notes

`generate-ldif` and `populate`/`run-all` create groups with different objectClass values:

| Mode | objectClass | Why |
|---|---|---|
| `generate-ldif` | `Group` (AD-style) | Matches the upstream `docker-test-openldap` image defaults |
| `populate` / `run-all` | `groupOfNames` (standard OpenLDAP) | Standard objectClass for runtime LDAP operations |

Set your Mattermost `LdapSettings.GroupFilter` accordingly:
- Using `generate-ldif`: `(objectClass=Group)`
- Using `populate` or `run-all`: `(objectClass=groupOfNames)`

See the [recommended Mattermost LDAP settings](getting-started.md#recommended-mattermost-ldap-settings) for a full working configuration.

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

## Running as a Python Module

```bash
python -m embiggenator generate-ldif -u 50 -o ./data
```

## Running Tests

```bash
pip install pytest
pytest
```
