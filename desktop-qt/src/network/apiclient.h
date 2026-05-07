#pragma once

#include <QString>

class QNetworkReply;
class QNetworkRequest;
class QUrl;

class ApiClient
{
public:
    explicit ApiClient(QString baseUrl = {});

    static void setGlobalToken(const QString &bearerToken);
    static void clearGlobalToken();
    [[nodiscard]] static QString globalToken();
    [[nodiscard]] static bool sessionExpired();
    static void clearSessionExpired();
    static void markSessionExpired();

    static void setGlobalBaseUrl(const QString &baseUrl);
    [[nodiscard]] static QString globalBaseUrl();

    [[nodiscard]] QString baseUrl() const;

protected:
    [[nodiscard]] QNetworkRequest makeAuthRequest(const QUrl &url) const;
    [[nodiscard]] static QByteArray waitForReply(QNetworkReply *reply, int timeoutMs, QString *errorMessage);

    QString m_baseUrl;

private:
    static QString s_bearerToken;
    static bool s_sessionExpired;
    static QString s_globalBaseUrl;
};
