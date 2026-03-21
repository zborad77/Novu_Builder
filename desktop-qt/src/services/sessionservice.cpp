#include "sessionservice.h"

#include <QSettings>

void SessionService::setTokens(const QString &accessToken, const QString &refreshToken)
{
    m_accessToken = accessToken;
    m_refreshToken = refreshToken;
}

QString SessionService::token() const
{
    return m_accessToken;
}

QString SessionService::refreshToken() const
{
    return m_refreshToken;
}

bool SessionService::isLoggedIn() const
{
    return !m_accessToken.isEmpty();
}

void SessionService::clear()
{
    m_accessToken.clear();
    m_refreshToken.clear();
    QSettings settings("NovuHub", "FotoNabidka");
    settings.remove("session/accessToken");
    settings.remove("session/refreshToken");
}

void SessionService::saveToSettings() const
{
    QSettings settings("NovuHub", "FotoNabidka");
    settings.setValue("session/accessToken", m_accessToken);
    settings.setValue("session/refreshToken", m_refreshToken);
}

void SessionService::loadFromSettings()
{
    QSettings settings("NovuHub", "FotoNabidka");
    m_accessToken = settings.value("session/accessToken").toString();
    m_refreshToken = settings.value("session/refreshToken").toString();
}
