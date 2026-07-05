#!/usr/bin/env bash
# Social Support Workflow Automation — one-command deploy
# Auto-detects macOS / Windows (WSL2 or Git Bash) / Linux (GPU or CPU),
# installs deps, pulls 3 models, starts services, seeds data, exposes the UI.
set -euo pipefail

# Color output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
step()  { echo ""; echo -e "${BOLD}── Step $1/8: $2 ${NC}(${3})"; }

START_TIME=$SECONDS

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "=================================================================="
echo "  Social Support Workflow Automation — one-command setup"
echo "=================================================================="
echo "  First run:       ~15-25 min (mostly model downloads, ~15 GB)"
echo "  Subsequent runs: ~1-2 min"
echo "  Everything is automatic — no input needed. Grab a coffee."
echo "=================================================================="

# ---------------------------------------------------------------------------
# 1. Detect OS + architecture
# ---------------------------------------------------------------------------
step 1 "Detect environment" "a few seconds"
OS="$(uname -s)"
ARCH="$(uname -m)"
PROFILE_OVERRIDE="${PROFILE:-}"
PROFILE="local"
LLM_MODEL="qwen3.5:9b"
VISION_MODEL="minicpm-v:8b"
EMBED_MODEL="bge-m3"
IS_WINDOWS=false
IS_WSL=false

if [[ "$OS" == "Darwin" ]]; then
  if [[ "$ARCH" == "arm64" ]]; then
    PROFILE="local"
    LLM_MODEL="qwen3.5:9b-mlx"
    ok "macOS Apple Silicon → profile=local, model=${LLM_MODEL}"
  else
    PROFILE="local"
    LLM_MODEL="qwen3.5:9b"
    ok "macOS Intel → profile=local, model=${LLM_MODEL}"
  fi
elif [[ "$OS" == "MINGW"* ]] || [[ "$OS" == "MSYS"* ]] || [[ "$OS" == "CYGWIN"* ]]; then
  IS_WINDOWS=true
  PROFILE="local"
  LLM_MODEL="qwen3.5:9b"
  ok "Windows (Git Bash/MSYS) → profile=local, model=${LLM_MODEL}"
elif [[ "$OS" == "Linux" ]]; then
  # Check if WSL
  if grep -qiE "(microsoft|wsl)" /proc/version 2>/dev/null; then
    IS_WSL=true
    IS_WINDOWS=true
    ok "Windows WSL2 detected → profile=local, model=${LLM_MODEL}"
  fi
  if command -v nvidia-smi &>/dev/null; then
    PROFILE="cloud"
    LLM_MODEL="qwen3.5:9b"
    ok "Linux + NVIDIA GPU → profile=cloud, model=${LLM_MODEL}"
  elif [[ "$IS_WSL" == false && -z "${DISPLAY:-}" ]]; then
    # Headless server without a GPU: still expose the public URL,
    # but CPU inference will be slow (minutes per application)
    PROFILE="cloud"
    warn "Headless Linux server without NVIDIA GPU → profile=cloud (public URL enabled)."
    warn "No GPU detected — LLM inference will run on CPU and be slow."
  else
    PROFILE="local"
    ok "Linux CPU-only → profile=local, model=${LLM_MODEL}"
  fi
else
  warn "Unknown OS: $OS — defaulting to profile=local, model=qwen3.5:9b"
fi

if [[ -n "$PROFILE_OVERRIDE" ]]; then
  PROFILE="$PROFILE_OVERRIDE"
  warn "Profile forced via PROFILE=${PROFILE}"
fi

export PROFILE LLM_MODEL VISION_MODEL EMBED_MODEL

# ---------------------------------------------------------------------------
# 2. Check + install dependencies
# ---------------------------------------------------------------------------
step 2 "Check dependencies (Docker, Ollama)" "~10 sec, or a few minutes if Docker/Ollama need installing"

# Docker — installed and started automatically when missing, so the same
# script works on a fresh Linux server, a Mac, or WSL2 without Docker Desktop.
install_docker() {
  if [[ "$OS" == "Darwin" ]]; then
    if ! command -v brew &>/dev/null; then
      err "Homebrew is required to install Docker on macOS. Install it from https://brew.sh and re-run."
      exit 1
    fi
    info "Installing Docker CLI + colima (no Docker Desktop required)..."
    brew install docker docker-compose colima
    mkdir -p "$HOME/.docker/cli-plugins"
    ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" "$HOME/.docker/cli-plugins/docker-compose"
  elif [[ "$IS_WINDOWS" == true && "$IS_WSL" == false ]]; then
    err "On native Windows, install Docker Desktop (https://docs.docker.com/desktop/install/windows-install/) or use WSL2, then re-run."
    exit 1
  else
    info "Installing Docker Engine (get.docker.com)..."
    curl -fsSL https://get.docker.com | sh
  fi
  ok "Docker installed"
}

start_docker_daemon() {
  info "Starting the Docker daemon..."
  if [[ "$OS" == "Darwin" ]]; then
    if command -v colima &>/dev/null; then
      colima start --cpu 4 --memory 8 --disk 40 || true
    else
      open -a Docker 2>/dev/null || true   # Docker Desktop, if that's what is installed
    fi
  else
    systemctl enable --now docker 2>/dev/null || sudo systemctl enable --now docker 2>/dev/null \
      || service docker start 2>/dev/null || sudo service docker start 2>/dev/null || true
    # No working service manager (minimal VMs, some containers): run dockerd directly
    if ! docker info &>/dev/null && command -v dockerd &>/dev/null; then
      info "No service manager available — launching dockerd directly..."
      nohup dockerd >/var/log/dockerd.log 2>&1 &
    fi
  fi
  for _ in $(seq 1 45); do
    docker info &>/dev/null && return 0
    sleep 2
  done
  return 1
}

if ! command -v docker &>/dev/null; then
  install_docker
fi

if ! docker info &>/dev/null; then
  # Non-root Linux user without docker-group membership: fall back to sudo
  if sudo -n docker info &>/dev/null 2>&1; then
    warn "Docker requires elevated permissions on this machine — using sudo for docker commands."
    docker() { sudo docker "$@"; }
  elif ! start_docker_daemon; then
    if [[ -f /.dockerenv ]]; then
      err "This environment is itself an unprivileged container (e.g. a RunPod/managed GPU pod),"
      err "so a Docker daemon cannot run inside it. This stack needs a real virtual machine."
      err "Use a VM-based GPU provider instead — Lambda Labs, AWS EC2 (g5.xlarge), GCP (L4),"
      err "or a Vast.ai 'VM' instance — then re-run: bash setup.sh"
    else
      err "Could not start the Docker daemon automatically. Check /var/log/dockerd.log, start it manually, and re-run."
    fi
    exit 1
  fi
fi
ok "Docker is running ($(docker --version))"

if docker compose version &>/dev/null 2>&1; then
  ok "Docker Compose $(docker compose version --short)"
else
  err "Docker Compose plugin not found. Install it: https://docs.docker.com/compose/install/"
  exit 1
fi

# Ollama — install + start daemon if missing
install_ollama() {
  if [[ "$OS" == "Darwin" ]]; then
    if command -v brew &>/dev/null; then
      brew install ollama
      brew services start ollama
    else
      err "Homebrew not found. Install from https://brew.sh or install Ollama from https://ollama.com/download/mac"
      exit 1
    fi
  elif [[ "$IS_WSL" == true ]]; then
    # In WSL, install via the official script
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl enable --now ollama 2>/dev/null || ollama serve &>/dev/null &
  elif [[ "$IS_WINDOWS" == true && "$IS_WSL" == false ]]; then
    # Native Windows (Git Bash) — can't install via script, prompt user
    err "On native Windows: install Ollama from https://ollama.com/download/windows"
    err "Then restart this script. Alternatively, use WSL2 for the Linux install path."
    exit 1
  else
    # Linux
    curl -fsSL https://ollama.com/install.sh | sh
    sudo systemctl enable --now ollama 2>/dev/null || true
  fi
}

if ! command -v ollama &>/dev/null; then
  info "Ollama not found. Installing..."
  install_ollama
  ok "Ollama installed"
else
  # Ensure daemon is running
  if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    warn "Ollama installed but daemon not responding. Starting..."
    if [[ "$OS" == "Darwin" ]]; then
      brew services start ollama 2>/dev/null || ollama serve &>/dev/null &
    elif [[ "$IS_WSL" == true ]]; then
      sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    else
      sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
    fi
    sleep 5
  fi
  ok "Ollama is running"
fi

# On Linux, containers reach the host's Ollama through the docker bridge —
# the default loopback-only bind would refuse them
if [[ "$OS" == "Linux" ]]; then
  if command -v systemctl &>/dev/null && systemctl list-unit-files ollama.service &>/dev/null; then
    (mkdir -p /etc/systemd/system/ollama.service.d 2>/dev/null || sudo mkdir -p /etc/systemd/system/ollama.service.d)
    printf "[Service]\nEnvironment=OLLAMA_HOST=0.0.0.0\n" > /tmp/ollama_override.conf
    (cp /tmp/ollama_override.conf /etc/systemd/system/ollama.service.d/override.conf 2>/dev/null \
      || sudo cp /tmp/ollama_override.conf /etc/systemd/system/ollama.service.d/override.conf)
    (systemctl daemon-reload && systemctl restart ollama) 2>/dev/null \
      || (sudo systemctl daemon-reload && sudo systemctl restart ollama) 2>/dev/null || true
    sleep 3
  elif ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    OLLAMA_HOST=0.0.0.0 nohup ollama serve > /var/log/ollama.log 2>&1 &
    sleep 5
  fi
fi

# Verify Ollama is actually responding
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
  err "Ollama daemon is not responding at http://localhost:11434"
  err "Try running 'ollama serve' in a separate terminal, then re-run this script."
  exit 1
fi
ok "Ollama API is responding"

# cloudflared (cloud profile only, for public tunnel)
if [[ "$PROFILE" == "cloud" ]]; then
  if ! command -v cloudflared &>/dev/null; then
    info "Installing cloudflared..."
    if [[ "$OS" == "Darwin" ]]; then
      brew install cloudflared
    else
      curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
      chmod +x /usr/local/bin/cloudflared
    fi
    ok "cloudflared installed"
  else
    ok "cloudflared available"
  fi
fi

# ---------------------------------------------------------------------------
# 3. Pull 3 models (~15 GB total)
# ---------------------------------------------------------------------------
step 3 "Pull 3 local models (~15 GB)" "~10-15 min on first run, seconds if cached"

info "  [1/3] Embedding model: $EMBED_MODEL (~1.2 GB, ~1 min)..."
ollama pull "$EMBED_MODEL"
ok "  Embedding model ready"

info "  [2/3] LLM (reasoning): $LLM_MODEL (~9 GB, ~6-10 min)..."
ollama pull "$LLM_MODEL"
ok "  LLM ready"

info "  [3/3] Vision LLM (OCR): $VISION_MODEL (~5.5 GB, ~4-6 min)..."
ollama pull "$VISION_MODEL"
ok "  Vision LLM ready"

ok "All 3 models pulled and served by Ollama at http://localhost:11434"

# ---------------------------------------------------------------------------
# 4. Smoke-test the OCR path before anything is built on top of it
# ---------------------------------------------------------------------------
step 4 "Smoke-test the vision/OCR path" "~30 sec (first model load)"
SMOKE_PY=$(cat <<'PYEOF'
import urllib.request, json, base64, sys
try:
    # Generate a simple test image with text
    from PIL import Image, ImageDraw
    import io
    img = Image.new("RGB", (400, 200), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Name: Test User", fill="black")
    d.text((10, 40), "ID: 784-1990-1234567-1", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()

    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps({
            "model": "minicpm-v:8b",
            "messages": [{"role": "user", "content": "Read all text on this image.", "images": [b64]}],
            "stream": False
        }).encode(),
        headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=120)
    d = json.loads(r.read())
    content = d.get("message", {}).get("content", "")
    if "Test" in content or "784" in content:
        print("OK")
    else:
        print("NO_MATCH:", content[:100])
except Exception as e:
    print("FAIL:", e, file=sys.stderr)
PYEOF
)

if echo "$SMOKE_PY" | python3 - 2>/dev/null | grep -q "OK"; then
  ok "OCR smoke-test passed — vision LLM reads image text correctly"
else
  warn "OCR smoke-test did not pass (model may still be loading). Continuing — full test runs later."
  warn "If OCR fails in the app, Tesseract is installed as a fallback in the Docker image."
fi

# ---------------------------------------------------------------------------
# 5. Generate .env + basic-auth credentials if missing
# ---------------------------------------------------------------------------
step 5 "Generate .env + credentials" "instant"
if [ ! -f .env ]; then
  info "Creating .env from .env.example..."
  cp .env.example .env
  # Generate a random API password for the demo
  if command -v openssl &>/dev/null; then
    GEN_PW=$(openssl rand -base64 12)
  else
    GEN_PW=$(date +%s | sha256sum | base64 | head -c 16)
  fi
  # Persist the detected profile + models so later `make up` runs match
  sed -i.bak "s/^VISION_MODEL=.*/VISION_MODEL=${VISION_MODEL}/; s/^LLM_MODEL=.*/LLM_MODEL=${LLM_MODEL}/; s/^PROFILE=.*/PROFILE=${PROFILE}/" .env 2>/dev/null || true
  rm -f .env.bak
  # Replace the placeholder password
  if [[ "$OS" == "Darwin" ]]; then
    sed -i '' "s/^API_PASSWORD=.*/API_PASSWORD=${GEN_PW}/" .env 2>/dev/null || true
  else
    sed -i "s/^API_PASSWORD=.*/API_PASSWORD=${GEN_PW}/" .env 2>/dev/null || true
  fi
  ok ".env created. API_PASSWORD=${GEN_PW}"
else
  ok ".env already exists"
fi

# ---------------------------------------------------------------------------
# 6. docker compose up (healthchecks gate next steps)
# ---------------------------------------------------------------------------
step 6 "Start all services (~10 containers)" "~3-5 min on first run (image builds), ~1 min after"
if [[ "$PROFILE" == "cloud" ]]; then
  # Caddy needs a bcrypt hash of the basic-auth password before it starts
  source .env 2>/dev/null || true
  BASIC_AUTH_HASH=$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "${API_PASSWORD:-change_me_in_prod}")
  export BASIC_AUTH_HASH
  ok "Basic-auth credentials hashed for the public URL"
fi
info "Starting: PostgreSQL, MongoDB, Qdrant, Neo4j, Langfuse, FastAPI, Streamlit, OpenWebUI..."
docker compose --profile "${PROFILE}" up -d
# Gate only on the app services — their dependencies (all databases, Langfuse)
# must be healthy first anyway; side tools like OpenWebUI never block the deploy
docker compose --profile "${PROFILE}" up -d --wait api ui
ok "All services are up:"
docker compose --profile "${PROFILE}" ps --format "        {{.Name}}  →  {{.Status}}"

# ---------------------------------------------------------------------------
# 7. Run seeder (one-shot: synthetic data + KB + graph + classifier + bias check)
# ---------------------------------------------------------------------------
step 7 "Seed data + train classifier" "~2-4 min"
info "200 synthetic applicants · 15 registry citizens with documents · Qdrant KB · Neo4j graph · classifier + bias check"
docker compose run --rm seeder python -m seeder.main
ok "Seeding complete"

# ---------------------------------------------------------------------------
# 8. Expose (branch by environment)
# ---------------------------------------------------------------------------
step 8 "Open the UI" "instant"
ELAPSED=$((SECONDS - START_TIME))
echo ""
echo "=================================================================="
ok "Social Support Workflow Automation is running! (took $((ELAPSED / 60))m $((ELAPSED % 60))s)"
echo "=================================================================="
echo ""
if [[ "$PROFILE" == "local" ]]; then
  info "Local UI:          http://localhost:8501"
  info "API docs (Swagger): http://localhost:8000/docs"
  info "Langfuse:          http://localhost:3000  (login: admin@sswa.local / sswa-admin-2026)"
  info "Neo4j browser:     http://localhost:7474"
  info "OpenWebUI:         http://localhost:8080"
  echo ""
  # Open browser on Mac / Windows
  if [[ "$OS" == "Darwin" ]]; then
    open http://localhost:8501 2>/dev/null || true
  elif [[ "$IS_WINDOWS" == true ]]; then
    cmd.exe /c start http://localhost:8501 2>/dev/null || true
  fi
else
  info "Starting public tunnel (cloudflared, runs in the background)..."
  nohup cloudflared tunnel --url http://localhost:80 > /tmp/cloudflared.log 2>&1 &
  TUNNEL_URL=""
  for _ in $(seq 1 30); do
    TUNNEL_URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/cloudflared.log 2>/dev/null | head -1 || true)
    [ -n "$TUNNEL_URL" ] && break
    sleep 2
  done
  if [ -n "$TUNNEL_URL" ]; then
    ok "Public URL:  ${TUNNEL_URL}  (gated by basic auth, survives this session)"
    info "Tunnel log:  /tmp/cloudflared.log — restart with: nohup cloudflared tunnel --url http://localhost:80 > /tmp/cloudflared.log 2>&1 &"
  else
    warn "Tunnel did not return a URL in time. Check /tmp/cloudflared.log."
    info "Local UI:    http://localhost:8501"
  fi
fi
echo ""
source .env 2>/dev/null || true
info "API username: ${API_USERNAME:-reviewer}"
info "API password: ${API_PASSWORD:-see .env}"
echo "=================================================================="
