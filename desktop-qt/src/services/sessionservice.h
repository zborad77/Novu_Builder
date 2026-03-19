#pragma once

#include <QString>

class SessionService
{
public:
    void setToken(const QString &token);
    [[nodiscard]] QString token() const;
    void clear();

private:
    QString m_token;
};
