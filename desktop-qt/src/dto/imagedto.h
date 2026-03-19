#pragma once

#include <QString>

struct ImageDto
{
    QString id;
    QString originalFilename;
    QString previewUrl;
    QString dimensionsLabel;
    QString processingStatus;
    int sortOrder = 0;
    bool isPrimary = false;
    bool isAnalysisReference = false;
};
