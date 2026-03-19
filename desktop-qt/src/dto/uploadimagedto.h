#pragma once

#include <QByteArray>
#include <QString>

struct UploadImageDto
{
    QString originalFilename;
    QString mimeType;
    QByteArray payload;
};
