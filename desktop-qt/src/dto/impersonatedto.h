#pragma once

#include <QString>

struct ImpersonateDto
{
    QString accessToken;
    QString userId;
    QString userEmail;
    QString userFullName;
    QString orgId;
    QString role;
    int expiresInMinutes = 15;
};
