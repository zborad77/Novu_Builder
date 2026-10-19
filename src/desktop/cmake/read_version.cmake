# cmake/read_version.cmake
# Cte verzi z version.json a generuje version.hpp z template.
# Volano jako custom target pred kazdym buildem NovuBuilder.
#
# Pouziti: cmake -DVERSION_FILE=<version.json>
#                -DTEMPLATE_FILE=<version.hpp.in>
#                -DOUTPUT_FILE=<version.hpp>
#                -P read_version.cmake

if(NOT VERSION_FILE)
    message(FATAL_ERROR "VERSION_FILE neni definovan")
endif()
if(NOT TEMPLATE_FILE)
    message(FATAL_ERROR "TEMPLATE_FILE neni definovan")
endif()
if(NOT OUTPUT_FILE)
    message(FATAL_ERROR "OUTPUT_FILE neni definovan")
endif()

if(NOT EXISTS "${VERSION_FILE}")
    message(FATAL_ERROR "version.json nenalezen: ${VERSION_FILE}")
endif()

file(READ "${VERSION_FILE}" VERSION_JSON)

string(REGEX MATCH "\"version\"[ \t]*:[ \t]*\"([0-9]+)\\.([0-9]+)\\.([0-9]+)\"" _match "${VERSION_JSON}")

if(NOT _match)
    message(FATAL_ERROR "Nepodarilo se parsovat verzi z ${VERSION_FILE}")
endif()

set(NOVU_VERSION_MAJOR "${CMAKE_MATCH_1}")
set(NOVU_VERSION_MINOR "${CMAKE_MATCH_2}")
set(NOVU_VERSION_PATCH "${CMAKE_MATCH_3}")

configure_file("${TEMPLATE_FILE}" "${OUTPUT_FILE}" @ONLY)

message(STATUS "[version] ${NOVU_VERSION_MAJOR}.${NOVU_VERSION_MINOR}.${NOVU_VERSION_PATCH} (from version.json)")
