#!/usr/bin/env bash
# G3: SIMOD 5.2.1 scopre uno scenario dal log di train di un log reale.
#
#   tests/simulation/benchmark/g3/discover.sh <log> <diff|fuzz|extr>
#   tests/simulation/benchmark/g3/discover.sh all        # i 3 log: diff, poi fuzz, poi extr
#
# <log> e' AcademicCredentials, BPIC_2012_W o BPIC_2017_W. Le configurazioni in
# configs/ sono quelle del benchmark di SIMOD (datasets/simod/config/benchmark)
# con i percorsi verso i nostri log. "diff": calendari fissi (CRISP), come lo
# scenario del paper; "fuzz": calendari FUZZY; "extr": calendari fissi e ritardi
# estranei (eclipse-aware). "fuzz" ed "extr" riusano il BPMN di "diff", come
# upstream: dopo una nuova "diff" vanno rifatte anche loro.
#
# Lo scenario migliore finisce in discovered/<log>_<variante>/, con il tempo di
# discovery in discovery.json; ci arriva solo se SIMOD riesce, altrimenti resta
# quello di prima e l'uscita e' diversa da 0. Con "all" un errore non ferma gli
# altri log (extr su AcademicCredentials crolla dentro SIMOD, vedi failures/).
#
# SIMOD gira in un venv suo (Python 3.12), come il runner: lo crea la prima volta.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
STACK_DIR="${VPT_STACK_DIR:-/var/tmp/delir-vpt-stack}"
VENV="$STACK_DIR/simod-venv"
WORK="${G3_WORK_DIR:-$STACK_DIR/simod-runs}"
SIMOD_SRC="${DELIR_DATASETS_CACHE:-$HOME/.cache/delir-datasets}/simod"

ensure_simod() {
  if [[ ! -x "$VENV/bin/simod" ]]; then
    command -v java >/dev/null || { echo "SIMOD richiede Java (Split Miner): installa un JDK" >&2; exit 1; }
    (cd "$ROOT" && uv run python scripts/fetch_datasets.py fetch simod)
    uv venv -q -p 3.12 "$VENV"
    VIRTUAL_ENV="$VENV" uv pip install -q "$SIMOD_SRC"
  fi
}

discover() {
  local log="$1" variant="$2"
  local config="$HERE/configs/${log}_${variant}.yml"
  local out="$HERE/discovered/${log}_${variant}"
  local run="$WORK/${log}_${variant}"
  local staged="$WORK/${log}_${variant}.scenario"
  [[ -f "$config" ]] || { echo "configurazione mancante: $config" >&2; return 2; }
  rm -rf "$run" "$staged" && mkdir -p "$run" "$staged"
  local started ended
  started=$(date +%s)
  if ! "$VENV/bin/simod" --configuration "$config" --output "$run" >"$run.log" 2>&1; then
    echo "$log $variant: SIMOD fallito, vedi $run.log; discovered/ non cambia" >&2
    return 1
  fi
  ended=$(date +%s)
  cp "$run/best_result/${log}_train.bpmn" "$staged/${log}.bpmn"
  cp "$run/best_result/${log}_train.json" "$staged/${log}.json"
  # Tempi per fase secondo SIMOD (la valutazione finale non fa parte della discovery).
  cp "$run/best_result/runtimes.json" "$staged/simod_runtimes.json"
  # Le distanze che SIMOD stesso calcola sul log di test, per confronto.
  if [[ -f "$run/best_result/evaluation/evaluation_metrics.csv" ]]; then
    cp "$run/best_result/evaluation/evaluation_metrics.csv" "$staged/simod_evaluation_metrics.csv"
  fi
  local version
  version=$("$VENV/bin/simod" --version | awk '{print $NF}')
  cat >"$staged/discovery.json" <<EOF
{
  "simod_version": "$version",
  "configuration": "configs/${log}_${variant}.yml",
  "discovery_seconds": $((ended - started)),
  "python": "$("$VENV/bin/python" -c 'import platform; print(platform.python_version())')",
  "java": "$(java -version 2>&1 | grep -m1 -E 'version' | sed 's/"/\\"/g')"
}
EOF
  rm -rf "$out" && mkdir -p "$(dirname "$out")" && mv "$staged" "$out"
  echo "$log $variant: $((ended - started)) s" >&2
}

# Tutto dentro main: bash legge lo script mentre gira, cosi' una modifica a meta'
# discovery non cambia la coda del run in corso.
main() {
  ensure_simod
  if [[ "${1:-}" == "all" ]]; then
    local failed=0
    for variant in diff fuzz extr; do
      for log in AcademicCredentials BPIC_2012_W BPIC_2017_W; do
        discover "$log" "$variant" || failed=1
      done
    done
    return "$failed"
  fi
  discover "${1:?log}" "${2:?diff, fuzz o extr}"
}

main "$@"
exit
