# Planka Repeater — Recurring Tasks Automation for Planka (Python)

> Automate recurring tasks in [Planka](https://github.com/plankanban/planka) using simple tags in card titles/descriptions: `[#R-D]`, `[#R-3D]`, `[#R-W]`, `[#R-2W]`, `[#R-M]`, `[#R-6M]`, etc. The service waits the specified period **after you move a card to *Done***, then automatically returns it to ***To Do***, and (optionally) updates the due date.
---

## ✨ What it does

* ✅ **Recurring tags** parsed from the **card title or description**:

  * `[R-D]` → every **day**
  * `[R-3D]` → every **3 days**
  * `[R-W]` → every **week**
  * `[R-2W]` → every **2 weeks**
  * `[R-M]` → every **month**
  * `[R-6M]` → every **6 months**
* ⏱️ **Delay-first logic**: when you move a card to **Done**, the service sets its `dueDate = now + period`. Only when `now >= dueDate` does it move the card back to **To Do** (bottom of list).
* 🔐 **.env support** via `python-dotenv` — no secrets in code.
* 🪪 **Robust login** to Planka API (works across slightly different responses).
* 🕰️ **Correct ISO 8601 UTC format** for `dueDate` (`YYYY-MM-DDTHH:MM:SS.000Z`).
* 🧰 Minimal dependencies: `requests`, `python-dateutil`, `python-dotenv`.

> Works great as a small companion service for teams that want lightweight recurring tasks in Planka.

---

## 🚀 Quick Start

```bash
# 1) Clone your repo and cd into it
# git clone https://github.com/your-org/planka-repeater.git
cd planka-repeater

# 2) Create & activate a virtualenv (recommended on Debian/Ubuntu due to PEP 668)
python3 -m venv venv
source venv/bin/activate

# 3) Install dependencies
pip install -r requirements.txt

# 4) Copy .env example and edit values
cp .env.example .env
# then edit .env with your Planka URL, credentials, board/list names

# 5) Run
python planka_repeater.py
```

---

## ⚙️ Configuration

Create a `.env` file in the project root:

```ini
PLANKA_BASE_URL=http://192.168.50.2:3000
PLANKA_USERNAME=admin
PLANKA_PASSWORD=changeme
BOARD_ID=1
TODO_LIST_NAME=To Do
DONE_LIST_NAME=Done
POLL_SECONDS=10
```

### Tags syntax

Use these tags in the **card title** or **description**:

```
[R-D]     # every day (defaults to 1)
[R-3D]    # every 3 days
[R-W]     # every week
[R-2W]    # every 2 weeks
[R-M]     # every month
[R-6M]    # every 6 months
```

> The number is optional; units are `D` (days), `W` (weeks), `M` (months).

---

## 🧠 How it works

1. The service polls your board at a short interval (`POLL_SECONDS`).
2. For cards in the **Done** list containing a recurrence tag:

   * If **no `dueDate`** (or it is in the past): it **schedules** the next run by setting `dueDate = now + period`.
   * If **`dueDate` has passed**: it **moves** the card back to **To Do** (bottom of list).
3. It remembers processed states to avoid flapping within the same poll cycle.

> `dueDate` is used as the timer while the card is in **Done**. If you prefer to keep `dueDate` for other purposes, you can extend the script to store the next run in a local `state.json` instead.

---

## 📦 Requirements

* **Python** 3.9+
* A reachable **Planka** instance and credentials with access to the target board
* Packages (via `requirements.txt`):

```txt
requests>=2.25.0
python-dateutil>=2.8.0
python-dotenv>=1.0.0
```

> On Debian/Ubuntu, use a **virtual environment** to avoid the PEP 668 "externally-managed-environment" error. See Troubleshooting below.

---

## 🛠️ Run as a service (systemd)

Create `/etc/systemd/system/planka-repeater.service`:

```ini
[Unit]
Description=Planka Repeater (Recurring Tasks)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/planka-repeater
ExecStart=/opt/planka-repeater/venv/bin/python /opt/planka-repeater/planka_repeater.py
EnvironmentFile=/opt/planka-repeater/.env
Restart=on-failure
RestartSec=5
User=planka
Group=planka

[Install]
WantedBy=multi-user.target
```

```bash
# Reload, enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now planka-repeater
sudo systemctl status planka-repeater -n 50
```

---

## 🐳 Docker (optional)

**Dockerfile**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY planka_repeater.py ./
CMD ["python", "planka_repeater.py"]
```

**docker-compose.yml**

```yaml
services:
  planka-repeater:
    build: .
    environment:
      PLANKA_BASE_URL: ${PLANKA_BASE_URL}
      PLANKA_USERNAME: ${PLANKA_USERNAME}
      PLANKA_PASSWORD: ${PLANKA_PASSWORD}
      BOARD_ID: ${BOARD_ID}
      TODO_LIST_NAME: ${TODO_LIST_NAME:-To Do}
      DONE_LIST_NAME: ${DONE_LIST_NAME:-Done}
      POLL_SECONDS: ${POLL_SECONDS:-10}
    restart: unless-stopped
```

> You can pass the same `.env` file to compose so it injects values automatically.

---

## 🔐 Security & best practices

* Create a **dedicated Planka user** with the minimum permissions required.
* Prefer **HTTPS** for `PLANKA_BASE_URL`.
* Keep credentials in `.env` (do **not** commit it).
* If you run this on a server, use a service user (e.g. `planka`) with limited rights.

---

## 🧩 Troubleshooting

### Lists not found

Ensure `TODO_LIST_NAME` / `DONE_LIST_NAME` match your Planka list names exactly.


## 🤝 Contributing

PRs welcome! Please open an issue describing your use case and environment.


## SEO notes

* Keywords: *Planka recurring tasks*, *Planka automation*, *Planka API Python*, *Kanban recurring cards*, *Planka scheduler*, *Planka dueDate format*, *python-dotenv*, *dateutil*, *requests*, *systemd service*, *Docker Planka*.
* Description: *Automate recurring tasks in Planka using simple `[R-…]` tags. Python service with .env support, robust API login, proper UTC ISO dates, and systemd/Docker deployment.*

