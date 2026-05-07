#pragma once

#include "apiclient.h"

#include <QPointF>
#include <QString>
#include <QVector>

class AnalysisApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] QString triggerAnalysisJob(
        const QString &caseId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QString getAnalysisJobStatus(
        const QString &jobId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool patchAnalysisSelection(
        const QString &caseId,
        const QString &analysisResultId,
        const QVector<QPointF> &polygon,
        double manualAreaSqm,
        QString *errorMessage = nullptr) const;
};
