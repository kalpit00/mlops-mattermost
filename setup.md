# Local Mattermost server + webapp (team notes)

Assumptions: you have cloned this repository, and Docker Desktop (or Docker Engine) is installed and running.

This describes the two-process dev flow (`webapp` webpack watch + `server` Go process). It also includes **one-time (per Postgres data volume) steps** that adjust **PostgreSQL inside the dev container**. Those steps are **not** changes to this repository’s application code; they compensate for how **Docker publishes** `localhost:5432` to the host and how the **official Postgres image** configures `pg_hba.conf` (only `127.0.0.1` / `::1` by default). In that setup, connections from the host often arrive at Postgres as the **Docker bridge / gateway** address (for example `192.168.65.1` on Docker Desktop for Mac, or `172.x` on Linux). That address is **not** loopback, so authentication fails unless you add broader `host` rules.

**Expect to run the Docker/`psql` section for every fresh clone or new Postgres volume**—do not wait for an error first.

---

## URLs

- **Web UI (default dev setup):** [http://localhost:8065](http://localhost:8065) (also `http://127.0.0.1:8065`)

The Go server listens on port **8065** and serves the client built under `webapp/channels/dist` (symlinked as `server/client`). Optional webpack dev-server (`cd webapp && make dev`) uses port **9005** with API traffic proxied to the server; the usual workflow is still to open **8065**.

---

## 1) Start Docker dependencies (before `make run` / `make run-server`)

From the `server` directory, bring containers up and wait until Postgres (and other enabled services) are ready:

```bash
cd server
make start-docker
```

This must complete **before** the `docker exec` / `psql` commands below, so the `mattermost-postgres` container exists.

---

## 2) PostgreSQL: apply container configuration (every new volume)

Defaults match `server/build/docker-compose.common.yml`: user **`mmuser`**, password **`mostest`**, database name **`mattermost_test`**.

### Allow TCP from any client address (worst-case Docker / VPN / bridge ranges)

We append a **local-dev-only** rule that matches **all IPv4 and IPv6** source addresses. Authentication remains **scram-sha-256** (not “trust”). Idempotent: skips if the marker line is already present.

```bash
docker exec mattermost-postgres sh -c \
  'grep -q "mattermost-dev-allow-docker-forward" /var/lib/postgresql/data/pg_hba.conf || \
   printf "%s\n" \
     "# mattermost-dev-allow-docker-forward (local dev; TCP via Docker-published ports)" \
     "host all all 0.0.0.0/0 scram-sha-256" \
     "host all all ::/0 scram-sha-256" >> /var/lib/postgresql/data/pg_hba.conf'
```

Reload configuration:

```bash
docker exec -e PGPASSWORD=mostest mattermost-postgres \
  psql -U mmuser -d postgres -h 127.0.0.1 -c "SELECT pg_reload_conf();"
```

### Create `mattermost_test` if the volume never created it

```bash
docker exec -e PGPASSWORD=mostest mattermost-postgres \
  psql -U mmuser -d postgres -h 127.0.0.1 -c \
  "CREATE DATABASE mattermost_test OWNER mmuser;" 2>/dev/null || true
```

(`CREATE DATABASE` errors if the DB already exists; `|| true` keeps copy-paste runs safe.)

---

## 3) Run the stack (two terminals)

**Terminal A — webapp (webpack watch):**

```bash
cd webapp
make run
```

**Terminal B — server:**

```bash
cd server
RUN_SERVER_IN_BACKGROUND=false make run-server
```

Why `RUN_SERVER_IN_BACKGROUND=false`: the server `Makefile` defaults `RUN_SERVER_IN_BACKGROUND` to `true` in `server/config.mk`, which backgrounds `go run` and exits `make` immediately. That can leave the server process easy to lose depending on your shell/session. Setting it to `false` keeps `go run` attached so logs stay in that terminal and the process keeps running as expected.

`make run-server` will start or reuse Docker services again as needed; the important part is that **section 2 ran after the first `make start-docker`** (or an equivalent first boot of Postgres) for that volume.

The first server start can take noticeable time while Go compiles and migrations run. You want a log line like **Server is listening on [::]:8065**.

---

## Optional reminders

- **Site URL:** logs may warn that SiteURL is unset; you can set it in the System Console after signup, or via config for stricter local setups.
- **Recreating the Postgres volume** (`docker volume rm`, new machine, etc.): repeat **section 2** for that volume.
