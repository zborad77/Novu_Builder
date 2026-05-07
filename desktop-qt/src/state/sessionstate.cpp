#include "sessionstate.h"

#include <QSettings>

#include "core/config.h"

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
    QSettings settings(Config::SettingsOrg, Config::SettingsApp);
    settings.remove(Config::KeySessionAccessToken);
    settings.remove(Config::KeySessionRefreshToken);
}

void SessionState::saveToSettings() const
{
    QSettings settings(Config::SettingsOrg, Config::SettingsApp);
    settings.setValue(Config::KeySessionAccessToken, m_accessToken);
    settings.setValue(Config::KeySessionRefreshToken, m_refreshToken);
}

void SessionState::loadFromSettings()
{
    QSettings settings(Config::SettingsOrg, Config::SettingsApp);
    m_accessToken = settings.value(Config::KeySessionAccessToken).toString();
    m_refreshToken = settings.value(Config::KeySessionRefreshToken).toString();
}
