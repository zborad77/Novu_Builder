#pragma once

#include "apiclient.h"
#include "models/casedto.h"
#include "models/proposaldraftpatchdto.h"

#include <QString>
#include <vector>

class CasesApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] std::vector<CaseDto> fetchCases(QString *errorMessage = nullptr) const;
    [[nodiscard]] QString createCase(
        const QString &title,
        const QString &addressLabel,
        const QString &repairScope,
        const QString &description,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QString duplicateCase(
        const QString &caseId,
        const QString &mode,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool sendCase(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto fetchCaseDetail(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto updateCaseProposalDraft(
        const QString &caseId,
        const ProposalDraftPatchDto &proposalDraft,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto createCaseFinalProposal(const QString &caseId, QString *errorMessage = nullptr) const;
};
