#pragma once

#include <QString>

struct AdminUserDto
{
    QString id;
    QString orgId;
    QString orgName;
    QString email;
    QString fullName;
    QString role;
    bool isActive = true;
    bool isSuperAdmin = false;
};
