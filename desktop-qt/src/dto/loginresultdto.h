#pragma once

#include <QString>

struct LoginResultDto
{
    QString accessToken;
    QString refreshToken;
    QString userId;
    QString email;
    QString fullName;
    QString role;
};
