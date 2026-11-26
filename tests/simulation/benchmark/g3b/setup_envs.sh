#!/usr/bin/env bash
# Ambienti di ricerca di G3b: uno per strumento, mai importati dal prodotto.
set -euo pipefail
C="${DELIR_DATASETS_CACHE:-$HOME/.cache/delir-datasets}"
E=/var/tmp/delir-g3b/envs
mkdir -p "$E"
[[ -x $E/simod/bin/simod ]] || { uv venv -q -p 3.12 $E/simod && VIRTUAL_ENV=$E/simod uv pip install -q "$C/simod" psutil; }
[[ -x $E/prosit/bin/python ]] && $E/prosit/bin/python -c "import prosit" 2>/dev/null || { uv venv -q -p 3.12 $E/prosit && VIRTUAL_ENV=$E/prosit uv pip install -q "$C/prosit" psutil typing_extensions; }
[[ -x $E/agentsim/bin/python ]] && $E/agentsim/bin/python -c "import mesa" 2>/dev/null || { uv venv -q -p 3.9 $E/agentsim && VIRTUAL_ENV=$E/agentsim uv pip install -q "Mesa==2.1.2" "pm4py==2.7.11.13" "polars==0.20.16" "pandas==2.2.2" "numpy==1.26.4" "scipy==1.13.1" "networkx==3.2.1" "scikit-learn==1.5.2" "pyarrow==17.0.0" pytz psutil "log-distance-measures==2.0.0"; }
[[ -x $E/atkde/bin/python ]] && $E/atkde/bin/python -c "import KDEpy" 2>/dev/null || { uv venv -q -p 3.12 $E/atkde && VIRTUAL_ENV=$E/atkde uv pip install -q "KDEpy==1.1.9" "scikit-learn==1.5.1" "scipy==1.14.0" "pandas==2.2.2" "numpy==1.26.4" tqdm matplotlib psutil "log-distance-measures==2.0.0"; }
echo envs ok
