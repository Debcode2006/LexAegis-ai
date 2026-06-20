# Docker for Beginners — LexAegis AI

This guide assumes you have **never used Docker**. It explains the concepts in
plain language, then walks you through running the entire LexAegis AI stack with
exact, copy-paste commands.

If you prefer clicking buttons over typing commands, read
[DOCKER_DESKTOP_GUIDE.md](DOCKER_DESKTOP_GUIDE.md) alongside this.

---

## Part 1 — The concepts

### 1. What is Docker?
Docker is a tool that packages an application **together with everything it needs
to run** (the right Python/Node version, libraries, system tools) into a single
unit. That unit runs the same way on your laptop, a colleague's machine, or a
cloud server. No more "but it works on my computer."

### 2. What is a container?
A **container** is a running instance of your app in its own isolated box. It has
its own filesystem and network, but shares your computer's operating system
kernel (so it's much lighter than a virtual machine). You can start, stop, and
delete containers freely. LexAegis runs **three** containers: frontend, backend,
and Chroma.

### 3. What is an image?
An **image** is the frozen blueprint a container is created from — like a class,
where a container is an object. You "build" an image once (from a `Dockerfile`),
then start as many containers from it as you want. Our images are built from
`frontend/Dockerfile` and `backend/Dockerfile`; Chroma uses a prebuilt image
downloaded from the internet.

### 4. What is a volume?
Containers are **disposable** — delete one and its internal files vanish. A
**volume** is storage that lives **outside** the container and **survives**
restarts, rebuilds, and deletion. LexAegis stores the Chroma vector database in a
volume called `chroma_data` so your uploaded documents and embeddings are not
lost when you rebuild.

### 5. What is Docker Compose?
Running three containers by hand (with the right ports, networks, and env vars)
is tedious. **Docker Compose** lets you describe all of them in one YAML file and
start everything with a single command. We ship two:

- `docker-compose.local.yml` — local dev (uses host Ollama)
- `docker-compose.production.yml` — production (uses Gemini)

---

## Part 2 — Step by step

### Step 1 — Install Docker Desktop
1. Go to <https://www.docker.com/products/docker-desktop/>.
2. Download the installer for your OS (Windows / Mac).
3. Run it and accept the defaults. On Windows, allow it to enable WSL 2 if asked.
4. Reboot if prompted.

### Step 2 — Launch Docker Desktop
1. Open **Docker Desktop** from your Start menu / Applications.
2. Wait until the whale icon in your taskbar stops animating and the dashboard
   says **"Docker Desktop is running"** (bottom-left status is green).
3. Leave it running — containers only work while Docker Desktop is up.

### Step 3 — Verify installation
Open a terminal (PowerShell on Windows) and run:

```bash
docker --version
docker compose version
```

You should see version numbers, e.g. `Docker version 27.x` and
`Docker Compose version v2.x`. If you get "command not found", Docker Desktop is
not running or not installed correctly — repeat Steps 1–2.

### Step 4 — Build the project
From the **repository root** (`lexaegis-ai/`):

```bash
# 1. Create the backend env file and fill in Supabase keys.
cp .env.example backend/.env
#    (open backend/.env in an editor; keep LLM_PROVIDER=ollama for local dev)

# 2. Build all images (frontend, backend). First build downloads a lot — be patient.
docker compose -f docker-compose.local.yml build
```

> Local mode uses **Ollama on your host**. In a separate terminal run
> `ollama serve` and make sure you've pulled the models once:
> `ollama pull qwen3 && ollama pull llama3.1 && ollama pull llama-guard3`.

### Step 5 — Start the project
```bash
docker compose -f docker-compose.local.yml up -d
```

`-d` means "detached" (runs in the background). Compose starts Chroma first,
waits until it's healthy, then starts the backend and frontend.

### Step 6 — Verify the project
```bash
# See the three containers and their health:
docker compose -f docker-compose.local.yml ps

# Check the backend is alive:
curl http://localhost:8000/api/v1/health

# Open the app:
#   http://localhost:3000   (frontend)
#   http://localhost:8000/docs  (backend API docs)
```

All three containers should show `running` and (after ~40s) `healthy`. For a full
end-to-end checklist see [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md).

### Step 7 — View logs
```bash
# Follow all logs (Ctrl+C to stop following — containers keep running):
docker compose -f docker-compose.local.yml logs -f

# Just one service:
docker compose -f docker-compose.local.yml logs -f backend
```

Look for `LLM_PROVIDER = ollama` and `[LLM HEALTH] Ollama reachable` in the
backend logs.

### Step 8 — Stop containers
```bash
# Stop and remove containers, keep the data volumes (your Chroma data is safe):
docker compose -f docker-compose.local.yml down

# Stop but DON'T remove (faster restart):
docker compose -f docker-compose.local.yml stop
```

### Step 9 — Restart containers
```bash
# If you used `stop`:
docker compose -f docker-compose.local.yml start

# Apply code changes (rebuild images, then restart):
docker compose -f docker-compose.local.yml up -d --build

# Restart a single service:
docker compose -f docker-compose.local.yml restart backend
```

---

## Persistent storage (volumes): location, backup, restore

### Where is it?
The Chroma data lives in a Docker-managed named volume. Find it:

```bash
docker volume ls                       # lists volumes (look for *_chroma_data)
docker volume inspect lexaegis-ai_chroma_data
```

The `Mountpoint` field is the on-disk path Docker manages (on Windows it's inside
the WSL VM, which is why you back it up with Docker commands, not by browsing
folders).

### Backup procedure
Copy the volume's contents into a tarball in your current directory:

```bash
docker run --rm \
  -v lexaegis-ai_chroma_data:/data \
  -v "$(pwd)":/backup \
  busybox tar czf /backup/chroma-backup.tar.gz -C /data .
```

You now have `chroma-backup.tar.gz`. Store it somewhere safe.

### Restore procedure
```bash
# Stop the stack first so nothing writes during restore:
docker compose -f docker-compose.local.yml down

# Extract the backup back into the volume:
docker run --rm \
  -v lexaegis-ai_chroma_data:/data \
  -v "$(pwd)":/backup \
  busybox sh -c "rm -rf /data/* && tar xzf /backup/chroma-backup.tar.gz -C /data"

# Start again:
docker compose -f docker-compose.local.yml up -d
```

> The volume name is `<project>_chroma_data`, where `<project>` is the folder name
> (`lexaegis-ai`). Confirm the exact name with `docker volume ls`.

---

## Common problems

| Symptom | Fix |
|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop isn't running — launch it (Step 2). |
| Backend logs `Ollama UNREACHABLE` | Run `ollama serve` on the host; confirm `OLLAMA_BASE_URL=http://host.docker.internal:11434`. |
| Port already in use (`:3000`/`:8000`) | Another process uses it — stop it, or change the host port in the compose file. |
| Frontend can't reach backend | `NEXT_PUBLIC_API_BASE` is baked at build — rebuild the frontend after changing it. |
| Changes not showing | You changed code but didn't rebuild: `up -d --build`. |

Next: [DOCKER_DESKTOP_GUIDE.md](DOCKER_DESKTOP_GUIDE.md) for the point-and-click
version of all of this.
