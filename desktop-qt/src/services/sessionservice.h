#pragma once

#include <QMutex>
#include <QString>
#include <memory>

class CaseActivityStreamClient;

class SessionService
{
public:
    SessionService();
    ~SessionService();

    void setTokens(const QString &accessToken, const QString &refreshToken);
    void setAccessToken(const QString &accessToken);
    [[nodiscard]] QString token() const;
    [[nodiscard]] QString refreshToken() const;
    [[nodiscard]] bool isLoggedIn() const;
    [[nodiscard]] bool isSessionExpired() const;
    void markSessionExpired();
    void clearSessionExpired();
    void clear();

    void saveToSettings() const;
    void loadFromSettings();
    void refreshRealtimeConnection();
    [[nodiscard]] CaseActivityStreamClient *caseActivityStreamClient() const;

private:
    void scheduleRealtimeRefresh();

    mutable QMutex m_mutex;
    QString m_accessToken;
    QString m_refreshToken;
    bool m_sessionExpired = false;
    std::unique_ptr<CaseActivityStreamClient> m_caseActivityStreamClient;
};
