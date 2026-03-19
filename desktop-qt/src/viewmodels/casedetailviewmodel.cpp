#include "casedetailviewmodel.h"

#include "services/apiservice.h"

CaseDto CaseDetailViewModel::loadCase(const QString &caseId, const ApiService &apiService)
{
    return apiService.fetchCaseDetail(caseId, &m_errorMessage);
}

std::vector<ImageDto> CaseDetailViewModel::loadCaseImages(const QString &caseId, const ApiService &apiService)
{
    return apiService.fetchCaseImages(caseId, &m_imageErrorMessage);
}

bool CaseDetailViewModel::setPrimaryImage(const QString &caseId, const QString &imageId, const ApiService &apiService)
{
    return apiService.setCasePrimaryImage(caseId, imageId, &m_imageErrorMessage);
}

bool CaseDetailViewModel::setAnalysisReferenceImage(const QString &caseId, const QString &imageId, const ApiService &apiService)
{
    return apiService.setCaseAnalysisReferenceImage(caseId, imageId, &m_imageErrorMessage);
}

QString CaseDetailViewModel::errorMessage() const
{
    return m_errorMessage;
}

QString CaseDetailViewModel::imageErrorMessage() const
{
    return m_imageErrorMessage;
}
