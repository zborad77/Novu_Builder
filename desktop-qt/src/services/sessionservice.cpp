#include "sessionservice.h"

#include <QMetaObject>
#include <QMutexLocker>
#include <QSettings>

#include "caseactivitystreamclient.h"

SessionService::SessionService()
    : m_caseActivityStreamClient(std::make_unique<CaseActivityStreamClient>(*this))
{
}

SessionService::~SessionService() = default;

void SessionService::setTokens(const QString &accessToken, const QString &refreshToken)
{
    QMutexLocker locker(&m_mutex);
    m_accessToken = accessToken;
    m_refreshToken = refreshToken;
    m_sessionExpired = false;
    locker.unlock();
    scheduleRealtimeRefresh();
}

void SessionService::setAccessToken(const QString &accessToken)
{
    QMutexLocker locker(&m_mutex);
    m_accessToken = accessToken;
    m_sessionExpired = false;
    locker.unlock();
    scheduleRealtimeRefresh();
}

QString SessionService::token() const
{
    QMutexLocker locker(&m_mutex);
    return m_accessToken;
}

QString SessionService::refreshToken() const
{
    QMutexLocker locker(&m_mutex);
    return m_refreshToken;
}

bool SessionService::isLoggedIn() const
{
    QMutexLocker locker(&m_mutex);
    return !m_accessToken.isEmpty();
}

bool SessionService::isSessionExpired() const
{
    QMutexLocker locker(&m_mutex);
    return m_sessionExpired;
}

void SessionService::markSessionExpired()
{
    {
        QMutexLocker locker(&m_mutex);
        m_accessToken.clear();
        m_refreshToken.clear();
        m_sessionExpired = true;
    }

    QSettings settings("NOVU", "NovuBuilder");
    settings.remove("session/accessToken");
    settings.remove("session/refreshToken");
    scheduleRealtimeRefresh();
}

void SessionService::clearSessionExpired()
{
    QMutexLocker locker(&m_mutex);
    m_sessionExpired = false;
}

void SessionService::clear()
{
    {
        QMutexLocker locker(&m_mutex);
        m_accessToken.clear();
        m_refreshToken.clear();
        m_sessionExpired = false;
    }

    QSettings settings("NOVU", "NovuBuilder");
    settings.remove("session/accessToken");
    settings.remove("session/refreshToken");
    scheduleRealtimeRefresh();
}

void SessionService::saveToSettings() const
{
    QMutexLocker locker(&m_mutex);
    QSettings settings("NOVU", "NovuBuilder");
    settings.setValue("session/accessToken", m_accessToken);
    settings.setValue("session/refreshToken", m_refreshToken);
}

void SessionService::loadFromSettings()
{
    QSettings settings("NOVU", "NovuBuilder");
    const QString accessToken = settings.value("session/accessToken").toString();
    const QString refreshToken = settings.value("session/refreshToken").toString();

    QMutexLocker locker(&m_mutex);
    m_accessToken = accessToken;
    m_refreshToken = refreshToken;
    m_sessionExpired = false;
    locker.unlock();
    scheduleRealtimeRefresh();
}

void SessionService::refreshRealtimeConnection()
{
    scheduleRealtimeRefresh();
}

CaseActivityStreamClient *SessionService::caseActivityStreamClient() const
{
    return m_caseActivityStreamClient.get();
}

void SessionService::scheduleRealtimeRefresh()
{
    auto *client = m_caseActivityStreamClient.get();
    if (!client) {
        return;
    }

    QMetaObject::invokeMethod(
        client,
        [client]() {
            client->refreshConnection();
        },
        Qt::QueuedConnection);
}
