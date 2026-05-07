#include "sessionstate.h"

#include <QSettings>

void SessionState::setTokens(const QString &accessToken, const QString &refreshToken)
{
    m_accessToken = accessToken;
    m_refreshToken = refreshToken;
}

QString SessionState::token() const
{
    return m_accessToken;
}

QString SessionState::refreshToken() const
{
    return m_refreshToken;
}

bool SessionState::isLoggedIn() const
{
    return !m_accessToken.isEmpty();
}

void SessionState::clear()
{
    m_accessToken.clear();
    m_refreshToken.clear();
    QSettings settings("NOVU", "NovuBuilder");
    settings.remove("session/accessToken");
    settings.remove("session/refreshToken");
}

void SessionState::saveToSettings() const
{
    QSettings settings("NOVU", "NovuBuilder");
    settings.setValue("session/accessToken", m_accessToken);
    settings.setValue("session/refreshToken", m_refreshToken);
}

void SessionState::loadFromSettings()
{
    QSettings settings("NOVU", "NovuBuilder");
    m_accessToken = settings.value("session/accessToken").toString();
    m_refreshToken = settings.value("session/refreshToken").toString();
}
