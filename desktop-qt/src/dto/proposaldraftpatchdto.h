#pragma once

#include <QString>

struct ProposalDraftPatchDto
{
    QString subject;
    QString summary;
    double materialCost = 0.0;
    double laborCost = 0.0;
    double amortization = 0.0;
    double margin = 0.0;
    QString recommendedSupplier;
    QString recommendedCompany;
};
