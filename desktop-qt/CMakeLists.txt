cmake_minimum_required(VERSION 3.21)

project(FotoNabidkaDesktop VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets Network)

qt_standard_project_setup()

qt_add_executable(FotoNabidkaDesktop
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
    src/dto/casedto.h
    src/dto/imagedto.h
    src/dto/logindto.h
    src/dto/uploadimagedto.h
    src/widgets/imageoverlaywidget.cpp
    src/widgets/imageoverlaywidget.h
    src/views/serversetupdialog.cpp
    src/views/serversetupdialog.h
)

target_include_directories(FotoNabidkaDesktop PRIVATE src)

target_link_libraries(FotoNabidkaDesktop PRIVATE Qt6::Widgets Qt6::Network)

set_target_properties(FotoNabidkaDesktop PROPERTIES
    WIN32_EXECUTABLE TRUE
)
