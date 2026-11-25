#!/bin/bash
set -euo pipefail

cd -- "$(dirname -- "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export ROLEMATCH_RUNTIME="${ROLEMATCH_RUNTIME:-$PWD/.local}"
export ROLEMATCH_OLLAMA_PORT="${ROLEMATCH_OLLAMA_PORT:-11435}"
export ROLEMATCH_VIEW="${ROLEMATCH_VIEW:-jobs}"
export PYTHONDONTWRITEBYTECODE=1
app_port="${ROLEMATCH_APP_PORT:-8501}"
app_url="http://127.0.0.1:$app_port"

if ! command -v python3.12 >/dev/null; then
    echo 'Install Python first with: brew install python@3.12'
    exit 1
fi
if [[ "$ROLEMATCH_VIEW" == 'portfolio' ]] && ! command -v ollama >/dev/null; then
    echo 'Install Ollama for the portfolio demo with: brew install ollama'
    exit 1
fi

if /usr/sbin/lsof -nP -iTCP:"$app_port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $app_port is already in use. If RoleMatch Local is running, open $app_url."
    exit 1
fi
if [[ "$ROLEMATCH_VIEW" == 'portfolio' ]] && /usr/sbin/lsof -nP -iTCP:"$ROLEMATCH_OLLAMA_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $ROLEMATCH_OLLAMA_PORT is already in use. Close the other portfolio demo first."
    exit 1
fi

setup_pid=""
ollama_pid=""
app_pid=""
cleanup() {
    if [[ -n "$setup_pid" ]]; then kill "$setup_pid" 2>/dev/null || true; fi
    if [[ -n "$app_pid" ]]; then kill "$app_pid" 2>/dev/null || true; fi
    if [[ -n "$ollama_pid" ]]; then kill "$ollama_pid" 2>/dev/null || true; fi
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_setup() {
    "$@" &
    setup_pid=$!
    wait "$setup_pid"
    setup_pid=""
}

mkdir -p "$ROLEMATCH_RUNTIME"
python_path="$ROLEMATCH_RUNTIME/venv/bin/python"
if [[ ! -x "$python_path" || ! -f "$ROLEMATCH_RUNTIME/venv/pyvenv.cfg" ]]; then
    run_setup python3.12 -m venv "$ROLEMATCH_RUNTIME/venv"
fi
if ! cmp -s requirements.txt "$ROLEMATCH_RUNTIME/installed-requirements.txt"; then
    run_setup "$python_path" -m pip install -r requirements.txt
    cp requirements.txt "$ROLEMATCH_RUNTIME/installed-requirements.txt"
fi

wait_for() {
    local url="$1" process="$2" attempt
    for (( attempt=0; attempt<100; attempt++ )); do
        if curl --noproxy '*' --silent --fail --max-time 1 "$url" >/dev/null; then return 0; fi
        if ! kill -0 "$process" 2>/dev/null; then return 1; fi
        sleep 0.25
    done
    return 1
}

if [[ "$ROLEMATCH_VIEW" == 'portfolio' ]]; then
    export OLLAMA_HOST="127.0.0.1:$ROLEMATCH_OLLAMA_PORT"
    export OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2
    export OLLAMA_MODELS="$ROLEMATCH_RUNTIME/models"
    mkdir -p "$OLLAMA_MODELS"
    ollama serve > "$ROLEMATCH_RUNTIME/ollama.log" 2>&1 &
    ollama_pid=$!
    if ! wait_for "http://$OLLAMA_HOST/api/version" "$ollama_pid"; then
        echo "Ollama did not start. See $ROLEMATCH_RUNTIME/ollama.log."
        exit 1
    fi
    for model in nomic-embed-text:v1.5 qwen3:4b-instruct; do
        if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fxq "$model"; then
            run_setup ollama pull "$model"
        fi
    done
fi

"$python_path" -m streamlit run app.py --server.port "$app_port" &
app_pid=$!
if ! wait_for "$app_url/_stcore/health" "$app_pid"; then
    echo 'Streamlit did not start. Check the output above.'
    exit 1
fi
echo "RoleMatch Local is running at $app_url. Press Ctrl+C to stop."
if [[ "${ROLEMATCH_NO_BROWSER:-0}" != "1" ]]; then
    /usr/bin/open "$app_url"
fi
wait "$app_pid"
