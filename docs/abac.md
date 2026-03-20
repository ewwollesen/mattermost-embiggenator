# ABAC Attributes

Every generated user gets custom LDAP attributes assigned by default, using standard `inetOrgPerson` attributes (no schema changes needed). These are useful for testing Attribute-Based Access Control (ABAC) policies out of the box.

## Default Attributes

| Attribute | Values | Distribution |
|---|---|---|
| `businessCategory` | `IL4`, `IL5`, `IL6` | Weighted (50/35/15) |
| `departmentNumber` | `Engineering`, `Sales`, `Support`, `Finance`, `HR` | Uniform |
| `employeeType` | `Full-Time`, `Contractor`, `Intern` | Weighted (70/20/10) |

The values are predictable and easy to find in the Mattermost UI or server logs.

## Custom Attributes

Specifying any custom ABAC attributes (via `--abac`, `--abac-profile`, or YAML config) **replaces the defaults entirely**.

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

Where `abac-attrs.yaml` follows the same format as the `abac:` section in the main config:

```yaml
attributes:
  - name: departmentNumber
    values: ["Engineering", "Sales", "Support"]
  - name: businessCategory
    values: ["Public", "Confidential", "Secret"]
    weights: [50, 30, 20]
```
