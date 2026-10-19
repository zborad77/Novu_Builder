#pragma once

#include <vector>

#include "models/casedto.h"
#include "models/imagedto.h"

class CasesApi;
class ImagesApi;

class CaseDetailViewModel
{
public:
    [[nodiscard]] CaseDto loadCase(const QString &caseId, const CasesApi &casesApi);
    [[nodiscard]] std::vector<ImageDto> loadCaseImages(const QString &caseId, const ImagesApi &imagesApi);
    [[nodiscard]] bool setPrimaryImage(const QString &caseId, const QString &imageId, const ImagesApi &imagesApi);
    [[nodiscard]] bool setAnalysisReferenceImage(const QString &caseId, const QString &imageId, const ImagesApi &imagesApi);
    [[nodiscard]] QString errorMessage() const;
    [[nodiscard]] QString imageErrorMessage() const;

private:
    QString m_errorMessage;
    QString m_imageErrorMessage;
};
