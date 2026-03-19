#pragma once

#include <QString>
#include <QStringList>

struct CaseDto
{
    QString id;
    QString title;
    QString status;
    bool isReferenceDataset = false;
    QString addressLabel;
    QString description;
    QString propertyType;
    QString repairScope;
    QString areaLabel;
    QString proposalStatus;
    QString proposalSubject;
    QString proposalSummary;
    QString proposalMaterialCostLabel;
    QString proposalLaborCostLabel;
    QString proposalAmortizationLabel;
    QString proposalMarginLabel;
    QString proposalTotalPriceLabel;
    QString proposalRecommendedSupplier;
    QString proposalRecommendedCompany;
    QStringList proposalWorkItems;
    QStringList proposalMaterials;
    QString expectedScope;
    QString expectedPrimaryFilename;
    QString expectedAnalysisReferenceFilename;
    QString referenceSourcePage;
    QString finalProposalStatus;
    QString finalProposalDraftVersionLabel;
    QString finalProposalSubject;
    QString finalProposalSummary;
    QString finalProposalTotalPriceLabel;
};
