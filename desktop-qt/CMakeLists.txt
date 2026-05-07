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
    src/ui/auth/loginview.cpp
    src/ui/auth/loginview.h
    src/ui/auth/serversetupdialog.cpp
    src/ui/auth/serversetupdialog.h
    src/ui/dashboard/dashboardview.cpp
    src/ui/dashboard/dashboardview.h
    src/ui/cases/caselistview.cpp
    src/ui/cases/caselistview.h
    src/ui/cases/casedetailview.cpp
    src/ui/cases/casedetailview.h
    src/ui/cases/newcaseview.cpp
    src/ui/cases/newcaseview.h
    src/ui/cases/casebrowserview.cpp
    src/ui/cases/casebrowserview.h
    src/ui/admin/adminpanelview.cpp
    src/ui/admin/adminpanelview.h
    src/ui/widgets/imageoverlaywidget.cpp
    src/ui/widgets/imageoverlaywidget.h
    src/viewmodels/loginviewmodel.cpp
    src/viewmodels/loginviewmodel.h
    src/viewmodels/dashboardviewmodel.cpp
    src/viewmodels/dashboardviewmodel.h
    src/viewmodels/caselistviewmodel.cpp
    src/viewmodels/caselistviewmodel.h
    src/viewmodels/casedetailviewmodel.cpp
    src/viewmodels/casedetailviewmodel.h
    src/network/apiclient.cpp
    src/network/apiclient.h
    src/network/authapi.cpp
    src/network/authapi.h
    src/network/casesapi.cpp
    src/network/casesapi.h
    src/services/apiservice.cpp
    src/services/apiservice.h
    src/state/sessionstate.cpp
    src/state/sessionstate.h
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
)

target_include_directories(NovuBuilder PRIVATE src)

target_link_libraries(NovuBuilder PRIVATE Qt6::Widgets Qt6::Network)

set_target_properties(NovuBuilder PROPERTIES
    WIN32_EXECUTABLE TRUE
)
