#pragma once

#include <QString>

class SessionService
{
public:
    void setTokens(const QString &accessToken, const QString &refreshToken);
    [[nodiscard]] QString token() const;
    [[nodiscard]] QString refreshToken() const;
    [[nodiscard]] bool isLoggedIn() const;
    void clear();

    void saveToSettings() const;
    void loadFromSettings();

private:
    QString m_accessToken;
    QString m_refreshToken;
};
