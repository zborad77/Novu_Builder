#include "sessionservice.h"

void SessionService::setToken(const QString &token)
{
    m_token = token;
}

QString SessionService::token() const
{
    return m_token;
}

void SessionService::clear()
{
    m_token.clear();
}
