#include "caselistviewmodel.h"

#include "network/casesapi.h"

std::vector<CaseDto> CaseListViewModel::loadCases(const CasesApi &apiService)
{
    auto cases = apiService.fetchCases(&m_errorMessage);
    return cases;
}

QString CaseListViewModel::duplicateCase(const QString &caseId, const QString &mode, const CasesApi &apiService)
{
    return apiService.duplicateCase(caseId, mode, &m_errorMessage);
}

QString CaseListViewModel::errorMessage() const
{
    return m_errorMessage;
}
