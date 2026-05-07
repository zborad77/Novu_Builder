#pragma once

#include <vector>

#include "models/casedto.h"
#include "models/imagedto.h"

class ApiService;

class CaseDetailViewModel
{
public:
    [[nodiscard]] CaseDto loadCase(const QString &caseId, const ApiService &apiService);
    [[nodiscard]] std::vector<ImageDto> loadCaseImages(const QString &caseId, const ApiService &apiService);
    [[nodiscard]] bool setPrimaryImage(const QString &caseId, const QString &imageId, const ApiService &apiService);
    [[nodiscard]] bool setAnalysisReferenceImage(const QString &caseId, const QString &imageId, const ApiService &apiService);
    [[nodiscard]] QString errorMessage() const;
    [[nodiscard]] QString imageErrorMessage() const;

private:
    QString m_errorMessage;
    QString m_imageErrorMessage;
};
