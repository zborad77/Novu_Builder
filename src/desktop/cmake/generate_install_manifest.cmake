# generate_install_manifest.cmake
# Reads version from version.json and writes install.manifest
#
# Required variables:
#   VERSION_FILE  - path to version.json
#   APP_NAME      - application slug (e.g. novu-builder-desktop)
#   OUTPUT_DIR    - directory where install.manifest will be written

file(READ "${VERSION_FILE}" VERSION_JSON)
string(JSON APP_VERSION GET "${VERSION_JSON}" "version")

set(MANIFEST_CONTENT "app=${APP_NAME}\nversion=${APP_VERSION}\nbuild=0\n")
file(WRITE "${OUTPUT_DIR}/install.manifest" "${MANIFEST_CONTENT}")

message(STATUS "[manifest] install.manifest: ${APP_NAME} v${APP_VERSION} -> ${OUTPUT_DIR}/install.manifest")
