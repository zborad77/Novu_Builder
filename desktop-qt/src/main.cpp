#include <QApplication>

#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("NOVU Builder");
    app.setOrganizationName("NOVU");

    MainWindow window;
    window.show();

    return app.exec();
}
