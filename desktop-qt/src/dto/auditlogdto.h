#pragma once

#include <QString>

struct AuditLogDto
{
    QString id;
    QString userId;
    QString userEmail;
    QString orgId;
    QString action;
    QString resourceType;
    QString resourceId;
    QString detail;
    QString impersonatedBy;
    QString ip;
    QString createdAt;
};
