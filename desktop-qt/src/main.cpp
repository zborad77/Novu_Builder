#include <QApplication>

#include "core/config.h"
#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName(Config::AppName);
    app.setOrganizationName(Config::OrgName);

    MainWindow window;
    window.show();

    return app.exec();
}
