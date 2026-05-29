#!/bin/sh
set -eu

REGISTRY="${REGISTRY:-ghcr.io/eu-farmbook}"
APP_IMAGE="${APP_IMAGE:-$REGISTRY/agri-tag}"
AGRI_EMBEDDING_MODEL="${AGRI_EMBEDDING_MODEL:-intfloat/multilingual-e5-small}"
PRELOAD_AGRI_MODEL="${PRELOAD_AGRI_MODEL:-false}"
TORCH_VERSION="${TORCH_VERSION:-2.11.0}"
TORCH_INDEX_URL="${TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"
PLATFORM="${PLATFORM:-linux/amd64}"
BUILD_ONLY="${BUILD_ONLY:-false}"
BUILDER_NAME="${BUILDER_NAME:-agri-tag-builder}"
TAG="${1:-latest}"

validate_tag() {
  case "$1" in
    ""|*[!A-Za-z0-9._-]*)
      echo "Invalid Docker tag: '$1'" >&2
      echo "Allowed characters: letters, digits, '.', '_' and '-'" >&2
      exit 1
      ;;
  esac
}

ensure_buildx() {
  if ! docker buildx version >/dev/null 2>&1; then
    echo "docker buildx is required but not available." >&2
    exit 1
  fi

  if ! docker buildx inspect "${BUILDER_NAME}" >/dev/null 2>&1; then
    docker buildx create --name "${BUILDER_NAME}" --use >/dev/null
  else
    docker buildx use "${BUILDER_NAME}" >/dev/null
  fi

  docker buildx inspect --bootstrap >/dev/null
}

ensure_registry_login() {
  if [ "${BUILD_ONLY}" = "true" ]; then
    return 0
  fi

  config_dir="${DOCKER_CONFIG:-$HOME/.docker}"
  config_file="${config_dir}/config.json"

  if [ ! -f "${config_file}" ]; then
    echo "Docker config not found at ${config_file}. Run 'docker login ${REGISTRY%%/*}' before pushing." >&2
    exit 1
  fi

  if grep -q "\"${REGISTRY%%/*}\"" "${config_file}" || grep -q '"credsStore"' "${config_file}" || grep -q '"credHelpers"' "${config_file}"; then
    return 0
  fi

  echo "No Docker credentials found for ${REGISTRY%%/*}. Run 'docker login ${REGISTRY%%/*}' before pushing." >&2
  exit 1
}

report_image_size() {
  image_ref="$1"
  if docker image inspect "${image_ref}" >/dev/null 2>&1; then
    docker image inspect "${image_ref}" --format 'Built image size: {{.Size}} bytes'
  fi
}

validate_tag "${TAG}"
ensure_buildx
ensure_registry_login

echo "Building app image: ${APP_IMAGE}:${TAG}"
echo "Embedding model: ${AGRI_EMBEDDING_MODEL}"
echo "Preload agriculture model: ${PRELOAD_AGRI_MODEL}"
echo "Platform: ${PLATFORM}"
echo "Build only: ${BUILD_ONLY}"

build_args="
  --pull
  --platform ${PLATFORM}
  --build-arg AGRI_EMBEDDING_MODEL=${AGRI_EMBEDDING_MODEL}
  --build-arg PRELOAD_AGRI_MODEL=${PRELOAD_AGRI_MODEL}
  --build-arg TORCH_VERSION=${TORCH_VERSION}
  --build-arg TORCH_INDEX_URL=${TORCH_INDEX_URL}
  -t ${APP_IMAGE}:${TAG}
"

if [ "${BUILD_ONLY}" = "true" ]; then
  docker buildx build \
    --load \
    ${build_args} \
    .
  report_image_size "${APP_IMAGE}:${TAG}"
else
  docker buildx build \
    --push \
    ${build_args} \
    .
fi

echo "Done."
echo "App image: ${APP_IMAGE}:${TAG}"
