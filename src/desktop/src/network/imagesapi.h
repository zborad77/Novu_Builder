#pragma once

#include "apiclient.h"
#include "models/imagedto.h"
#include "models/uploadimagedto.h"

#include <QByteArray>
#include <QString>
#include <vector>

class ImagesApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] std::vector<ImageDto> fetchCaseImages(
        const QString &caseId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<ImageDto> moveCaseImage(
        const QString &caseId,
        const QString &imageId,
        const QString &direction,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCasePrimaryImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCaseAnalysisReferenceImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool uploadCaseImages(
        const QString &caseId,
        const std::vector<UploadImageDto> &images,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QByteArray fetchImageData(
        const QString &imageUrl,
        QString *errorMessage = nullptr) const;
};
