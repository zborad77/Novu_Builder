#include <QApplication>
#include <QEventLoop>
#include <QJsonDocument>
#include <QMessageBox>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

#include "mainwindow.h"

namespace {
bool backendHealthLooksReady(QString *errorMessage)
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl("http://127.0.0.1:8000/api/v1/health"));
    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(2500);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Backend health check selhal: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return false;
    }

    const auto payload = reply->readAll();
    reply->deleteLater();
    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend health vratil neplatnou JSON odpoved.";
        }
        return false;
    }

    const auto object = document.object();
    const auto ready = object.value("ready").toBool(true);
    if (!ready && errorMessage) {
        *errorMessage = "Backend neni pripraveny. Zkontroluj startup checks a database/storage readiness.";
    }
    return ready;
}
}

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName("FotoNabidka Desktop");
    app.setOrganizationName("NOVU");

    MainWindow window;
    window.show();

    QString startupError;
    if (!backendHealthLooksReady(&startupError)) {
        QMessageBox::warning(
            &window,
            "Backend startup kontrola",
            startupError.isEmpty()
                ? "Backend zatim nevypada pripraveny. Aplikace pobezi, ale workflow muze byt omezeny."
                : startupError
        );
    }

    return app.exec();
}
