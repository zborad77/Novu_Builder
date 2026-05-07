#include "authapi.h"

#include <QEventLoop>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

LoginResultDto AuthApi::login(const QString &email, const QString &password, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }
    if (m_baseUrl.trimmed().isEmpty()) {
        if (errorMessage) {
            *errorMessage = QString::fromUtf8("Server neni nastaven. Nejdrive nastavte URL firemniho NOVU serveru.");
        }
        return {};
    }

    QJsonObject body;
    body["email"] = email;
    body["password"] = password;

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/auth/login"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
        loop.quit();
    });
    timeoutTimer.start(8000);
    loop.exec();

    const auto httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (httpStatus == 0) {
        reply->deleteLater();
        if (errorMessage) {
            *errorMessage = "Backend neni dostupny. Zkontroluj zda bezi server.";
        }
        return {};
    }
    const auto responseData = reply->readAll();
    reply->deleteLater();

    const auto doc = QJsonDocument::fromJson(responseData);
    if (!doc.isObject()) {
        if (errorMessage) {
            *errorMessage = "Neplatna odpoved serveru.";
        }
        return {};
    }

    if (httpStatus != 200) {
        if (errorMessage) {
            const auto detail = doc.object().value("detail").toString();
            *errorMessage = detail.isEmpty() ? "Prihlaseni se nezdarilo." : detail;
        }
        return {};
    }

    const auto root = doc.object();
    const auto user = root.value("user").toObject();
    return LoginResultDto{
        .accessToken = root.value("accessToken").toString(),
        .refreshToken = root.value("refreshToken").toString(),
        .userId = user.value("id").toString(),
        .email = user.value("email").toString(),
        .fullName = user.value("fullName").toString(),
        .role = user.value("role").toString(),
        .isSuperAdmin = user.value("isSuperAdmin").toBool(),
    };
}
