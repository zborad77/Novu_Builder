#include "apiclient.h"

#include <QEventLoop>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

QString ApiClient::s_bearerToken;
bool ApiClient::s_sessionExpired = false;
QString ApiClient::s_globalBaseUrl;

ApiClient::ApiClient(QString baseUrl)
    : m_baseUrl(baseUrl.isEmpty() ? globalBaseUrl() : std::move(baseUrl))
{
}

QString ApiClient::baseUrl() const
{
    return m_baseUrl;
}

void ApiClient::setGlobalToken(const QString &bearerToken)
{
    s_bearerToken = bearerToken;
    s_sessionExpired = false;
}

void ApiClient::clearGlobalToken()
{
    s_bearerToken.clear();
}

QString ApiClient::globalToken()
{
    return s_bearerToken;
}

bool ApiClient::sessionExpired()
{
    return s_sessionExpired;
}

void ApiClient::clearSessionExpired()
{
    s_sessionExpired = false;
}

void ApiClient::markSessionExpired()
{
    s_sessionExpired = true;
    s_bearerToken.clear();
}

void ApiClient::setGlobalBaseUrl(const QString &baseUrl)
{
    QString normalized = baseUrl.trimmed();
    while (normalized.endsWith('/')) {
        normalized.chop(1);
    }
    s_globalBaseUrl = normalized;
}

QString ApiClient::globalBaseUrl()
{
    return s_globalBaseUrl;
}

QNetworkRequest ApiClient::makeAuthRequest(const QUrl &url) const
{
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    if (!s_bearerToken.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + s_bearerToken.toUtf8());
    }
    return request;
}

QByteArray ApiClient::waitForReply(QNetworkReply *reply, int timeoutMs, QString *errorMessage)
{
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    bool timedOut = false;

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]() {
        timedOut = true;
        if (reply->isRunning()) {
            reply->abort();
        }
        loop.quit();
    });

    timer.start(timeoutMs);
    loop.exec();

    const int httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();

    if (timedOut || reply->error() == QNetworkReply::OperationCanceledError) {
        reply->deleteLater();
        if (errorMessage) {
            *errorMessage = "Timeout — server neodpovida. Zkontroluj zda bezi backend.";
        }
        return {};
    }

    if (httpStatus == 401) {
        reply->deleteLater();
        ApiClient::markSessionExpired();
        if (errorMessage) {
            *errorMessage = "Relace vyprsela. Prihlaste se znovu.";
        }
        return {};
    }

    if (reply->error() != QNetworkReply::NoError && httpStatus == 0) {
        const auto err = reply->error();
        const auto errStr = reply->errorString();
        reply->deleteLater();
        if (errorMessage) {
            if (err == QNetworkReply::SslHandshakeFailedError) {
                *errorMessage = "Chyba TLS/SSL: nelze overit certifikat serveru.";
            } else {
                *errorMessage = QString("Sit'ova chyba: %1").arg(errStr);
            }
        }
        return {};
    }

    const QByteArray body = reply->readAll();
    reply->deleteLater();

    if (httpStatus >= 400) {
        if (errorMessage) {
            if (httpStatus == 403) {
                *errorMessage = "Pristup zamitnuto. Kontaktujte spravce.";
            } else if (httpStatus == 422) {
                const auto doc = QJsonDocument::fromJson(body);
                const auto detail = doc.isObject() ? doc.object().value("detail").toString() : QString();
                *errorMessage = detail.isEmpty() ? "Neplatna data. Zkontrolujte vyplnena pole." : detail;
            } else if (httpStatus == 429) {
                *errorMessage = "Prilis mnoho pozadavku. Pockejte chvili a zkuste znovu.";
            } else if (httpStatus == 503) {
                *errorMessage = "Server je docasne nedostupny. Zkuste znovu za chvili.";
            } else {
                const auto doc = QJsonDocument::fromJson(body);
                const auto detail = doc.isObject() ? doc.object().value("detail").toString() : QString();
                *errorMessage = detail.isEmpty()
                    ? QString("Chyba serveru (%1).").arg(httpStatus)
                    : detail;
            }
        }
        return {};
    }

    return body;
}
