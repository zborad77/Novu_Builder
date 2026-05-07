#include "casedetailviewmodel.h"

#include "network/casesapi.h"
#include "network/imagesapi.h"

CaseDto CaseDetailViewModel::loadCase(const QString &caseId, const CasesApi &casesApi)
{
    return casesApi.fetchCaseDetail(caseId, &m_errorMessage);
}

std::vector<ImageDto> CaseDetailViewModel::loadCaseImages(const QString &caseId, const ImagesApi &imagesApi)
{
    return imagesApi.fetchCaseImages(caseId, &m_imageErrorMessage);
}

bool CaseDetailViewModel::setPrimaryImage(const QString &caseId, const QString &imageId, const ImagesApi &imagesApi)
{
    return imagesApi.setCasePrimaryImage(caseId, imageId, &m_imageErrorMessage);
}

bool CaseDetailViewModel::setAnalysisReferenceImage(const QString &caseId, const QString &imageId, const ImagesApi &imagesApi)
{
    return imagesApi.setCaseAnalysisReferenceImage(caseId, imageId, &m_imageErrorMessage);
}

QString CaseDetailViewModel::errorMessage() const
{
    return m_errorMessage;
}

QString CaseDetailViewModel::imageErrorMessage() const
{
    return m_imageErrorMessage;
}
