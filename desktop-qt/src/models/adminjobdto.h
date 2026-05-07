#pragma once

#include <QString>

struct AdminJobDto
{
    QString id;
    QString caseId;
    QString caseTitle;
    QString orgId;
    QString orgName;
    QString status;
    QString jobType;
    QString startedAt;
    QString finishedAt;
    QString errorMessage;
    QString createdAt;
};
