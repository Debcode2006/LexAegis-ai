# Docker Desktop Guide — LexAegis AI (click by click)

The same operations as [DOCKER_FOR_BEGINNERS.md](DOCKER_FOR_BEGINNERS.md), but
using the **Docker Desktop graphical app** instead of the terminal. Written for
someone who has never opened Docker Desktop before.

Throughout, the **left sidebar** of Docker Desktop has these tabs:
**Containers · Images · Volumes · Builds · Docker Hub**. (Networks are visible
via container details and the CLI.)

> You still build/start the stack once from a terminal (Docker Desktop has no
> "open my compose file" button for an arbitrary project). After that, everything
> below is done by clicking.
>
> One-time start from the repo root:
> ```bash
> docker compose -f docker-compose.local.yml up -d --build
> ```

---

## Containers tab

This is your home base. It lists everything running.

**What you'll see:** a group named **lexaegis-ai** (the compose project) with
three rows: `lexaegis-frontend`, `lexaegis-backend`, `lexaegis-chroma`. Each row
shows a status dot (green = running), the image, the published port, and action
buttons on the right (**Start ▶ / Stop ■ / Restart ⟳ / Delete 🗑**).

### How to inspect a container
1. Click the container's **name** (e.g. `lexaegis-backend`).
2. You land on a detail page with tabs across the top:
   - **Logs** — live output (see below).
   - **Inspect** — the full JSON config: env vars, mounts, networks, ports.
   - **Bind mounts / Exec / Files / Stats**.
3. The **Files** tab lets you browse the container's filesystem (e.g. look inside
   `/app/.data`).
4. The **Exec** tab opens a terminal *inside* the container — type commands like
   `env | grep LLM_PROVIDER` to confirm configuration.
5. The **Stats** tab shows live CPU / memory / network usage.

### How to inspect logs
1. Click the container name → **Logs** tab.
2. Logs stream live. Use the **search box** to filter (e.g. type `LLM HEALTH` or
   `GEMINI`).
3. For the backend, confirm you see `LLM_PROVIDER = ollama` (or `gemini`) and a
   `[LLM HEALTH]` line. Errors appear in red/yellow.
4. The **Download** / copy icons save logs for sharing.

### How to restart a service
- In the Containers list, hover the row → click the **⟳ Restart** icon, **or**
- Open the container → top-right **Restart** button.
- Use this after changing an environment variable in the compose file (you must
  re-run `up` from the terminal for env changes; Restart alone reuses old config).

### How to delete a service
1. Hover the container row → click **■ Stop** first (you can't delete a running
   container).
2. Click the **🗑 Delete** icon → confirm.
3. To remove the whole project group, stop all three then delete each — or from a
   terminal: `docker compose -f docker-compose.local.yml down`.
4. **Deleting a container does NOT delete its volume** — your Chroma data is safe
   (see Volumes tab).

### How to rebuild a service
Docker Desktop doesn't rebuild a compose service from the GUI. Rebuild from a
terminal, then the new container appears in the GUI automatically:
```bash
docker compose -f docker-compose.local.yml up -d --build backend
```

---

## Images tab

**What you'll see:** the images built/downloaded for the project —
`lexaegis-ai-frontend`, `lexaegis-ai-backend`, and `chromadb/chroma`. Each shows
its size and tag.

- Click an image to see its **layers** and which containers use it.
- **In use** images have a green tag; unused ones can be removed.
- To reclaim disk space, select unused images → **Delete**, or use the **Clean
  up** button. (Deleting an image used by a stopped container forces a rebuild
  next time.)

---

## Volumes tab

This is where your **persistent data** lives. **This is the important one** — your
Chroma vector database survives here.

**What you'll see:** a volume named like `lexaegis-ai_chroma_data` and
`lexaegis-ai_backend_data`.

### How to inspect persistent storage
1. Click the **Volumes** tab.
2. Click `lexaegis-ai_chroma_data`.
3. The detail view shows:
   - **In Use By** — which container mounts it (the backend/Chroma).
   - **Stored data** / a file browser — drill into the actual files Chroma wrote.
   - Size on disk.
4. To confirm persistence: stop and delete the Chroma container, then come back —
   the volume (and its files) is still here. Start the stack again and your data
   reappears.

> **Do not** click Delete on `chroma_data` unless you intend to wipe every
> uploaded document and embedding. There is no undo.

---

## Networks

Compose automatically creates a private network (e.g. `lexaegis-ai_default`) so
the containers can talk to each other by name (`backend` → `chroma`).

To inspect it:
1. Open any container → **Inspect** tab → search for `Networks`.
2. You'll see the network name and the container's internal IP.
3. (CLI equivalent: `docker network ls` and `docker network inspect lexaegis-ai_default`.)

This network is why the backend uses `CHROMA_HOST=chroma` instead of an IP — the
service name resolves on this network. The browser, being **outside** this
network, instead uses `localhost:8000`.

---

## Logs (project-wide)

For a combined view across all three services, the terminal is clearer:
```bash
docker compose -f docker-compose.local.yml logs -f
```
In the GUI, open each container's **Logs** tab individually.

---

## Quick reference: GUI action → what it does

| I want to…                  | In Docker Desktop                                   |
|-----------------------------|-----------------------------------------------------|
| See what's running          | **Containers** tab                                  |
| Read errors                 | Container → **Logs** tab                             |
| Run a command inside        | Container → **Exec** tab                             |
| Check env/config            | Container → **Inspect** tab                          |
| Restart a service           | Container row → **⟳**                                |
| Stop everything             | Stop each container, or `compose down` (terminal)   |
| Free disk space             | **Images** / **Volumes** → delete unused            |
| Confirm data persists       | **Volumes** → `chroma_data` → file browser          |
| Rebuild after code change   | terminal: `compose up -d --build`                   |

See also [DEPLOYMENT_VALIDATION.md](DEPLOYMENT_VALIDATION.md) to verify the whole
system end-to-end.
