#pragma once

#include "apiclient.h"
#include "models/exportdto.h"

#include <QByteArray>
#include <QString>

class ExportsApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] ExportDto triggerExport(
        const QString &caseId,
        const QString &exportType,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QByteArray downloadExportFile(
        const QString &downloadUrl,
        QString *errorMessage = nullptr) const;
};
