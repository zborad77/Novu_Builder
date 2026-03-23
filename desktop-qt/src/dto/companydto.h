#pragma once

#include <QString>

struct CompanyDto
{
    QString id;
    QString name;
    QString ico;
    QString email;
    QString phone;
    int userCount = 0;
};
