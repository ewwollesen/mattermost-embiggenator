# Docker Compose Examples

## Volume Mount (Recommended)

Generate LDIF files first, then mount them into the container:

```bash
embiggenator generate-ldif -u 500 -g 20 -m 10-50 -o ./embiggenator-data
```

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

```bash
docker compose up -d
```

The `50_` prefix on generated files ensures they load after the built-in defaults.

## Sidecar Container

Build and run Embiggenator as a sidecar that populates the LDAP server on startup:

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

## Working Examples

See the [`examples/`](../examples/) directory for complete, working Docker Compose configurations:

- [`docker-compose.yml`](../examples/docker-compose.yml) -- volume mount approach
- [`docker-compose.sidecar.yml`](../examples/docker-compose.sidecar.yml) -- sidecar approach
- [`embiggenator.yaml`](../examples/embiggenator.yaml) -- example config file
