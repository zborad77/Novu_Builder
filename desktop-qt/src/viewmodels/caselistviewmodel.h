#pragma once

#include <QString>
#include <vector>

#include "models/casedto.h"

#include "network/casesapi.h"

class CaseListViewModel
{
public:
    [[nodiscard]] std::vector<CaseDto> loadCases(const CasesApi &apiService);
    [[nodiscard]] QString duplicateCase(const QString &caseId, const QString &mode, const CasesApi &apiService);
    [[nodiscard]] QString errorMessage() const;

private:
    QString m_errorMessage;
};
