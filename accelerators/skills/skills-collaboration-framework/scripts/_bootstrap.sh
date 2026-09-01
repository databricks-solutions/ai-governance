# Shared Python-dependency bootstrap — SOURCE this, don't execute it.
#   source "$(dirname "$0")/_bootstrap.sh"
#   ensure_pydeps yaml            # guarantee PyYAML is importable
#   ensure_pydeps yaml sqlglot    # ...plus optional extras
#
# "It just works": a user runs a script, the script guarantees its own deps. Already-present
# envs skip the install entirely; a genuinely missing, uninstallable dep fails LOUD with a clear
# message rather than a downstream ModuleNotFoundError. Maps import name -> pip package where they
# differ (yaml -> pyyaml).

_pip_name() {
  case "$1" in
    yaml) echo "pyyaml" ;;
    *)    echo "$1" ;;
  esac
}

ensure_pydeps() {
  local mod
  for mod in "$@"; do
    if python3 -c "import $mod" 2>/dev/null; then
      continue
    fi
    local pkg; pkg="$(_pip_name "$mod")"
    python3 -m pip install "$pkg" -q 2>/dev/null || pip install "$pkg" -q 2>/dev/null || {
      echo "ERROR: Python module '$mod' is required but could not be installed (pip install $pkg failed)." >&2
      exit 1
    }
    python3 -c "import $mod" 2>/dev/null || {
      echo "ERROR: installed '$pkg' but '$mod' is still not importable." >&2
      exit 1
    }
  done
}
