#include <QApplication>

#include "mainwindow.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("FotoNabidka Desktop");
    app.setOrganizationName("NOVU");

    MainWindow window;
    window.show();

    return app.exec();
}
