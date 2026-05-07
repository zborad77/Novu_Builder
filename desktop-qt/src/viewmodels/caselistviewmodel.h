#pragma once

#include <QString>
#include <vector>

#include "models/casedto.h"

class ApiService;

class CaseListViewModel
{
public:
    [[nodiscard]] std::vector<CaseDto> loadCases(const ApiService &apiService);
    [[nodiscard]] QString duplicateCase(const QString &caseId, const QString &mode, const ApiService &apiService);
    [[nodiscard]] QString errorMessage() const;

private:
    QString m_errorMessage;
};
