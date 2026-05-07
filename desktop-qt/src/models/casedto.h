#pragma once

#include <QString>
#include <QPointF>
#include <QStringList>
#include <QVector>

struct CaseDto
{
    QString id;
    QString title;
    QString status;
    bool isReferenceDataset = false;
    QString source; // "mobile" | "desktop"
    QString addressLabel;
    QString createdByName;
    QString description;
    QString propertyType;
    QString repairScope;
    QString areaLabel;
    QString proposalStatus;
    QString workflowAnalysisStatus;
    QString workflowDraftStatus;
    bool workflowCanCreateFinalProposal = false;
    bool workflowCanSend = false;
    QStringList workflowBlockingReasons;
    QString proposalSubject;
    QString proposalSummary;
    QString proposalMaterialCostLabel;
    QString proposalLaborCostLabel;
    QString proposalTransportCostLabel;
    QString proposalAmortizationLabel;
    QString proposalMarginLabel;
    QString proposalTotalPriceLabel;
    QString proposalRecommendedSupplier;
    QString proposalRecommendedCompany;
    QStringList proposalWorkItems;
    QStringList proposalMaterials;
    // Materiály s cenami (name | qty unit | unitPrice | total)
    struct ProposalMaterialItem {
        QString name;
        double quantity = 0.0;
        QString unit;
        double unitPrice = 0.0;
        double totalPrice = 0.0;
    };
    QList<ProposalMaterialItem> proposalMaterialItems;
    QString expectedScope;
    QString expectedPrimaryFilename;
    QString expectedAnalysisReferenceFilename;
    QString referenceSourcePage;
    QString finalProposalStatus;
    QString workflowFinalProposalStatus;
    QString finalProposalDraftVersionLabel;
    QString finalProposalSubject;
    QString finalProposalSummary;
    QString finalProposalTotalPriceLabel;

    // Analyza
    bool hasAnalysis = false;
    QString analysisId;
    QString analysisObjectType;
    QString analysisSurfaceCondition;
    QString analysisRecommendedScope;
    double analysisEstimatedAreaSqm = 0.0;
    double analysisAreaConfidence = 0.0;
    double analysisDurationDays = 0.0;
    double analysisLaborHours = 0.0;
    QStringList analysisWorkflowSteps;   // formatovane: "1. Název (Xh) — popis"
    QStringList analysisMaterialItems;   // formatovane: "Název — qty unit × price = total CZK"
    QVector<QPointF> analysisMaskPolygon; // normalizovane body AI maskovaci oblasti [0,1]

    // 3 cenove varianty
    bool hasQuoteVariants = false;
    QString quoteEconomyLabel;
    QString quoteStandardLabel;
    QString quotePremiumLabel;
    double quoteEconomyTotalIncVat = 0.0;
    double quoteStandardTotalIncVat = 0.0;
    double quotePremiumTotalIncVat = 0.0;
};
