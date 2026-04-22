find_package(Qt6 REQUIRED COMPONENTS Test Network WebSockets)

qt_add_executable(tst_caseactivityservice
    tst_caseactivityservice.cpp
    ../src/services/caseactivityservice.cpp
    ../src/services/apiservice.cpp
    ../src/services/caseactivitystreamclient.cpp
    ../src/services/sessionservice.cpp
)

target_include_directories(tst_caseactivityservice PRIVATE ../src)

target_link_libraries(tst_caseactivityservice PRIVATE
    Qt6::Test
    Qt6::Network
    Qt6::WebSockets
)

add_test(NAME tst_caseactivityservice COMMAND tst_caseactivityservice)
