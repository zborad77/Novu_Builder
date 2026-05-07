cmake_minimum_required(VERSION 3.21)

project(NovuBuilder VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Network)

qt_standard_project_setup()

qt_add_executable(NovuBuilder
    src/main.cpp
    src/mainwindow.cpp
    src/mainwindow.h
    src/views/loginview.cpp
    src/views/loginview.h
    src/views/dashboardview.cpp
    src/views/dashboardview.h
    src/views/caselistview.cpp
    src/views/caselistview.h
    src/views/casedetailview.cpp
    src/views/casedetailview.h
    src/views/newcaseview.cpp
    src/views/newcaseview.h
    src/views/casebrowserview.cpp
    src/views/casebrowserview.h
    src/views/adminpanelview.cpp
    src/views/adminpanelview.h
    src/viewmodels/loginviewmodel.cpp
    src/viewmodels/loginviewmodel.h
    src/viewmodels/dashboardviewmodel.cpp
    src/viewmodels/dashboardviewmodel.h
    src/viewmodels/caselistviewmodel.cpp
    src/viewmodels/caselistviewmodel.h
    src/viewmodels/casedetailviewmodel.cpp
    src/viewmodels/casedetailviewmodel.h
    src/services/apiservice.cpp
    src/services/apiservice.h
    src/services/sessionservice.cpp
    src/services/sessionservice.h
    src/models/adminjobdto.h
    src/models/adminuserdto.h
    src/models/auditlogdto.h
    src/models/casedto.h
    src/models/companydto.h
    src/models/exportdto.h
    src/models/imagedto.h
    src/models/impersonatedto.h
    src/models/logindto.h
    src/models/loginresultdto.h
    src/models/proposaldraftpatchdto.h
    src/models/uploadimagedto.h
    src/widgets/imageoverlaywidget.cpp
    src/widgets/imageoverlaywidget.h
    src/views/serversetupdialog.cpp
    src/views/serversetupdialog.h
)

target_include_directories(NovuBuilder PRIVATE src)

target_link_libraries(NovuBuilder PRIVATE Qt6::Widgets Qt6::Network)

set_target_properties(NovuBuilder PROPERTIES
    WIN32_EXECUTABLE TRUE
)
