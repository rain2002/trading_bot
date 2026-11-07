#!/usr/bin/env bash
# Wrapper redirecting to root deploy_gcp.sh
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "${SCRIPT_DIR}/../../deploy_gcp.sh" "$@"
