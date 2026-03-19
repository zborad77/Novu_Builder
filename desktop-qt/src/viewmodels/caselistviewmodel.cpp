#include "caselistviewmodel.h"

#include "services/apiservice.h"

std::vector<CaseDto> CaseListViewModel::loadCases(const ApiService &apiService)
{
    auto cases = apiService.fetchCases(&m_errorMessage);
    return cases;
}

QString CaseListViewModel::duplicateCase(const QString &caseId, const QString &mode, const ApiService &apiService)
{
    return apiService.duplicateCase(caseId, mode, &m_errorMessage);
}

QString CaseListViewModel::errorMessage() const
{
    return m_errorMessage;
}
