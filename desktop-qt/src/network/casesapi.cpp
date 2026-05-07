#include "casesapi.h"

#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointF>
#include <QUrl>
#include <QVector>

namespace {
QString formatCurrencyLabel(const QJsonValue &value)
{
    if (!value.isDouble()) {
        return {};
    }

    return QString::number(value.toDouble(), 'f', 2) + " CZK";
}

CaseDto parseCaseDetailResponse(const QByteArray &payload, QString *errorMessage)
{
    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved pro detail case.";
        }
        return {};
    }

    const auto rootObject = document.object();
    const auto location = rootObject.value("location").toObject();
    const auto latestAnalysis = rootObject.value("latestAnalysis").toObject();
    const auto proposalDraft = rootObject.value("proposalDraft").toObject();
    const auto finalProposal = rootObject.value("finalProposal").toObject();
    const auto workflowStatus = rootObject.value("workflowStatus").toObject();
    const auto blockingReasons = workflowStatus.value("blockingReasons").toArray();
    const auto referenceExpectations = rootObject.value("referenceExpectations").toObject();
    const auto suggestedWorkItems = proposalDraft.value("suggestedWorkItems").toArray();
    const auto materials = proposalDraft.value("materials").toArray();

    QString areaLabel;
    const auto manualArea = latestAnalysis.value("manualAreaSqm");
    const auto estimatedArea = latestAnalysis.value("estimatedAreaSqm");
    if (manualArea.isDouble()) {
        areaLabel = QString::number(manualArea.toDouble(), 'f', 1) + " m2 manual";
    } else if (estimatedArea.isDouble()) {
        areaLabel = QString::number(estimatedArea.toDouble(), 'f', 1) + " m2 AI";
    }

    QStringList proposalWorkItems;
    proposalWorkItems.reserve(suggestedWorkItems.size());
    for (const auto &itemValue : suggestedWorkItems) {
        const auto itemObject = itemValue.toObject();
        QString label = itemObject.value("name").toString();
        const auto note = itemObject.value("note").toString();
        if (!note.isEmpty()) {
            label += " - " + note;
        }
        if (!label.isEmpty()) {
            proposalWorkItems.push_back(label);
        }
    }

    QStringList proposalMaterials;
    QList<CaseDto::ProposalMaterialItem> proposalMaterialItems;
    proposalMaterials.reserve(materials.size());
    proposalMaterialItems.reserve(materials.size());
    for (const auto &itemValue : materials) {
        const auto itemObject = itemValue.toObject();
        const QString name = itemObject.value("name").toString();
        const double qty = itemObject.value("quantity").toDouble();
        const QString unit = itemObject.value("unit").toString();
        const double unitPrice = itemObject.value("unitPrice").toDouble();
        const double totalPrice = itemObject.value("totalPrice").toDouble();
        const bool hasQty = itemObject.value("quantity").isDouble() && !unit.isEmpty();
        const bool hasUnitPrice = itemObject.value("unitPrice").isDouble();
        const bool hasTotalPrice = itemObject.value("totalPrice").isDouble();
        proposalMaterialItems.push_back({name, qty, unit, unitPrice, totalPrice});
        QString label = name;
        if (hasQty) {
            label += QString(" — %1 %2").arg(qty, 0, 'f', 1).arg(unit);
        }
        if (hasQty && hasUnitPrice) {
            label += QString(" × %1 CZK").arg(unitPrice, 0, 'f', 2);
        }
        if (hasTotalPrice) {
            label += QString(" = %1 CZK").arg(totalPrice, 0, 'f', 2);
        }
        if (!label.isEmpty()) {
            proposalMaterials.push_back(label);
        }
    }

    QStringList workflowBlockingReasons;
    workflowBlockingReasons.reserve(blockingReasons.size());
    for (const auto &reasonValue : blockingReasons) {
        const auto reason = reasonValue.toString().trimmed();
        if (!reason.isEmpty()) {
            workflowBlockingReasons.push_back(reason);
        }
    }

    // --- latestAnalysis ---
    const bool hasAnalysis = !latestAnalysis.isEmpty() && !latestAnalysis.value("id").toString().isEmpty();
    QStringList analysisWorkflowSteps;
    QStringList analysisMaterialItems;
    QVector<QPointF> analysisMaskPolygon;
    if (hasAnalysis) {
        const auto maskPts = latestAnalysis.value("maskPolygon").toArray();
        analysisMaskPolygon.reserve(maskPts.size());
        for (const auto &ptValue : maskPts) {
            const auto pt = ptValue.toObject();
            analysisMaskPolygon.append({pt.value("x").toDouble(), pt.value("y").toDouble()});
        }
        const auto wfSteps = latestAnalysis.value("workflowSteps").toArray();
        int autoIndex = 1;
        for (const auto &stepValue : wfSteps) {
            QString label;
            if (stepValue.isString()) {
                // bootstrap formát: prostý string
                label = QString("%1. %2").arg(autoIndex).arg(stepValue.toString());
            } else {
                const auto step = stepValue.toObject();
                const int stepNum = step.value("step").toInt(autoIndex);
                const QString name = step.value("name").toString();
                const double hours = step.value("estimatedHours").toDouble();
                const QString desc = step.value("description").toString();
                label = QString("%1. %2").arg(stepNum).arg(name);
                if (hours > 0) {
                    label += QString(" (%1 h)").arg(hours, 0, 'f', 1);
                }
                if (!desc.isEmpty()) {
                    label += " — " + desc;
                }
            }
            if (!label.isEmpty()) {
                analysisWorkflowSteps.push_back(label);
            }
            ++autoIndex;
        }
        const auto aMaterials = latestAnalysis.value("materials").toArray();
        for (const auto &matValue : aMaterials) {
            const auto mat = matValue.toObject();
            QString label = mat.value("name").toString();
            const bool hasQty = mat.value("quantity").isDouble() && !mat.value("unit").toString().isEmpty();
            if (hasQty) {
                label += QString(" — %1 %2")
                    .arg(mat.value("quantity").toDouble(), 0, 'f', 1)
                    .arg(mat.value("unit").toString());
            }
            if (hasQty && mat.value("unitPrice").isDouble()) {
                label += QString(" × %1 CZK").arg(mat.value("unitPrice").toDouble(), 0, 'f', 2);
            }
            if (mat.value("totalPrice").isDouble()) {
                label += QString(" = %1 CZK").arg(mat.value("totalPrice").toDouble(), 0, 'f', 2);
            }
            if (!label.isEmpty()) {
                analysisMaterialItems.push_back(label);
            }
        }
    }

    // --- quoteVariants ---
    const auto quoteVariantsArray = rootObject.value("quoteVariants").toArray();
    bool hasQuoteVariants = !quoteVariantsArray.isEmpty();
    QString quoteEconomyLabel, quoteStandardLabel, quotePremiumLabel;
    double quoteEconomyTotal = 0.0, quoteStandardTotal = 0.0, quotePremiumTotal = 0.0;
    for (const auto &variantValue : quoteVariantsArray) {
        const auto variant = variantValue.toObject();
        const QString vtype = variant.value("variantType").toString();
        const double total = variant.value("totalIncVat").toDouble();
        const double labor = variant.value("laborCost").toDouble();
        const double material = variant.value("materialCost").toDouble();
        const QString label = QString("%1 CZK (práce %2 + mat. %3)")
            .arg(total, 0, 'f', 0)
            .arg(labor, 0, 'f', 0)
            .arg(material, 0, 'f', 0);
        if (vtype == "economy") { quoteEconomyLabel = label; quoteEconomyTotal = total; }
        else if (vtype == "standard") { quoteStandardLabel = label; quoteStandardTotal = total; }
        else if (vtype == "premium") { quotePremiumLabel = label; quotePremiumTotal = total; }
    }

    return {
        .id = rootObject.value("id").toString(),
        .title = rootObject.value("title").toString(),
        .status = rootObject.value("status").toString(),
        .isReferenceDataset = rootObject.value("isReferenceDataset").toBool(),
        .source = rootObject.value("source").toString("mobile"),
        .addressLabel = location.value("addressLabel").toString(),
        .description = rootObject.value("description").toString(),
        .propertyType = rootObject.value("propertyType").toString(),
        .repairScope = rootObject.value("repairScope").toString(),
        .areaLabel = areaLabel,
        .proposalStatus = proposalDraft.value("status").toString(),
        .workflowAnalysisStatus = workflowStatus.value("analysisStatus").toString(),
        .workflowDraftStatus = workflowStatus.value("draftStatus").toString(),
        .workflowCanCreateFinalProposal = workflowStatus.value("canCreateFinalProposal").toBool(),
        .workflowCanSend = workflowStatus.value("canSend").toBool(),
        .workflowBlockingReasons = workflowBlockingReasons,
        .proposalSubject = proposalDraft.value("subject").toString(),
        .proposalSummary = proposalDraft.value("summary").toString(),
        .proposalMaterialCostLabel = formatCurrencyLabel(proposalDraft.value("materialCost")),
        .proposalLaborCostLabel = formatCurrencyLabel(proposalDraft.value("laborCost")),
        .proposalTransportCostLabel = formatCurrencyLabel(proposalDraft.value("transportCost")),
        .proposalAmortizationLabel = formatCurrencyLabel(proposalDraft.value("amortization")),
        .proposalMarginLabel = formatCurrencyLabel(proposalDraft.value("margin")),
        .proposalTotalPriceLabel = formatCurrencyLabel(proposalDraft.value("totalPrice")),
        .proposalRecommendedSupplier = proposalDraft.value("recommendedSupplier").toString(),
        .proposalRecommendedCompany = proposalDraft.value("recommendedCompany").toString(),
        .proposalWorkItems = proposalWorkItems,
        .proposalMaterials = proposalMaterials,
        .proposalMaterialItems = proposalMaterialItems,
        .expectedScope = referenceExpectations.value("expectedScope").toString(),
        .expectedPrimaryFilename = referenceExpectations.value("expectedPrimaryFilename").toString(),
        .expectedAnalysisReferenceFilename = referenceExpectations.value("expectedAnalysisReferenceFilename").toString(),
        .referenceSourcePage = referenceExpectations.value("sourcePage").toString(),
        .finalProposalStatus = finalProposal.value("status").toString(),
        .workflowFinalProposalStatus = workflowStatus.value("finalProposalStatus").toString(),
        .finalProposalDraftVersionLabel = finalProposal.value("draftVersion").isDouble()
            ? QString("Draft verze %1").arg(finalProposal.value("draftVersion").toInt())
            : QString(),
        .finalProposalSubject = finalProposal.value("subject").toString(),
        .finalProposalSummary = finalProposal.value("summary").toString(),
        .finalProposalTotalPriceLabel = formatCurrencyLabel(finalProposal.value("totalPrice")),
        .hasAnalysis = hasAnalysis,
        .analysisId = latestAnalysis.value("id").toString(),
        .analysisObjectType = latestAnalysis.value("objectType").toString(),
        .analysisSurfaceCondition = latestAnalysis.value("surfaceCondition").toString(),
        .analysisRecommendedScope = latestAnalysis.value("recommendedScope").toString(),
        .analysisEstimatedAreaSqm = latestAnalysis.value("estimatedAreaSqm").toDouble(),
        .analysisAreaConfidence = latestAnalysis.value("areaConfidence").toDouble(),
        .analysisDurationDays = latestAnalysis.value("estimatedDurationDays").toDouble(),
        .analysisLaborHours = latestAnalysis.value("laborHoursTotal").toDouble(),
        .analysisWorkflowSteps = analysisWorkflowSteps,
        .analysisMaterialItems = analysisMaterialItems,
        .analysisMaskPolygon = analysisMaskPolygon,
        .hasQuoteVariants = hasQuoteVariants,
        .quoteEconomyLabel = quoteEconomyLabel,
        .quoteStandardLabel = quoteStandardLabel,
        .quotePremiumLabel = quotePremiumLabel,
        .quoteEconomyTotalIncVat = quoteEconomyTotal,
        .quoteStandardTotalIncVat = quoteStandardTotal,
        .quotePremiumTotalIncVat = quotePremiumTotal,
    };
}

} // namespace

std::vector<CaseDto> CasesApi::fetchCases(QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + "/cases")));
    const auto payload = waitForReply(reply, 5000, errorMessage);
    if (payload.isNull()) {
        return {};
    }

    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved pro seznam cases.";
        }
        return {};
    }

    const auto rootObject = document.object();
    const auto items = rootObject.value("items").toArray();

    std::vector<CaseDto> result;
    result.reserve(static_cast<size_t>(items.size()));
    for (const auto &itemValue : items) {
        const auto itemObject = itemValue.toObject();
        result.push_back(
            {
                .id = itemObject.value("id").toString(),
                .title = itemObject.value("title").toString(),
                .status = itemObject.value("status").toString(),
                .isReferenceDataset = itemObject.value("isReferenceDataset").toBool(),
                .addressLabel = itemObject.value("addressLabel").toString(),
                .createdByName = itemObject.value("createdByName").toString(),
                .description = {},
                .propertyType = itemObject.value("propertyType").toString(),
                .repairScope = itemObject.value("repairScope").toString(),
                .areaLabel = itemObject.value("estimatedAreaSqm").isDouble()
                    ? QString::number(itemObject.value("estimatedAreaSqm").toDouble(), 'f', 1) + " m2"
                    : QString(),
                .proposalStatus = {},
                .proposalSubject = {},
                .proposalSummary = {},
                .proposalMaterialCostLabel = {},
                .proposalLaborCostLabel = {},
                .proposalAmortizationLabel = {},
                .proposalMarginLabel = {},
                .proposalTotalPriceLabel = {},
                .proposalRecommendedSupplier = {},
                .proposalRecommendedCompany = {},
                .proposalWorkItems = {},
                .proposalMaterials = {},
                .finalProposalStatus = {},
                .finalProposalDraftVersionLabel = {},
                .finalProposalSubject = {},
                .finalProposalSummary = {},
                .finalProposalTotalPriceLabel = {}
            }
        );
    }

    return result;
}

QString CasesApi::createCase(
    const QString &title,
    const QString &addressLabel,
    const QString &repairScope,
    const QString &description,
    QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QJsonObject body;
    body["title"] = title;
    body["source"] = QStringLiteral("desktop");
    if (!addressLabel.isEmpty()) body["addressLabel"] = addressLabel;
    if (!repairScope.isEmpty()) body["repairScope"] = repairScope;
    if (!description.isEmpty()) body["description"] = description;

    QNetworkAccessManager manager;
    auto *reply = manager.post(makeAuthRequest(QUrl(m_baseUrl + "/cases")),
                               QJsonDocument(body).toJson(QJsonDocument::Compact));
    const auto payload = waitForReply(reply, 10000, errorMessage);
    if (payload.isNull()) return {};
    if (sessionExpired()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    return doc.object().value("id").toString();
}

QString CasesApi::duplicateCase(const QString &caseId, const QString &mode, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    const auto body = QJsonDocument(QJsonObject{{"mode", mode}}).toJson(QJsonDocument::Compact);
    auto *reply = manager.post(makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/duplicate")), body);
    const auto responsePayload = waitForReply(reply, 5000, errorMessage);
    if (responsePayload.isNull()) {
        return {};
    }

    const auto document = QJsonDocument::fromJson(responsePayload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved pro kopii zakazky.";
        }
        return {};
    }

    const auto duplicatedId = document.object().value("id").toString();
    if (duplicatedId.isEmpty() && errorMessage) {
        *errorMessage = "Backend nevratil id nove kopie zakazky.";
    }
    return duplicatedId;
}

bool CasesApi::sendCase(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.post(makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/send")), QByteArray());
    QString localError;
    const auto responsePayload = waitForReply(reply, 5000, &localError);
    if (responsePayload.isNull()) {
        if (errorMessage) {
            *errorMessage = localError;
        }
        return false;
    }
    return true;
}

CaseDto CasesApi::fetchCaseDetail(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId)));
    const auto payload = waitForReply(reply, 5000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return parseCaseDetailResponse(payload, errorMessage);
}

CaseDto CasesApi::updateCaseProposalDraft(
    const QString &caseId,
    const ProposalDraftPatchDto &proposalDraft,
    QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    const auto body = QJsonDocument(QJsonObject{
        {"subject", proposalDraft.subject},
        {"summary", proposalDraft.summary},
        {"materialCost", proposalDraft.materialCost},
        {"laborCost", proposalDraft.laborCost},
        {"transportCost", proposalDraft.transportCost},
        {"amortization", proposalDraft.amortization},
        {"margin", proposalDraft.margin},
        {"recommendedSupplier", proposalDraft.recommendedSupplier},
        {"recommendedCompany", proposalDraft.recommendedCompany},
    }).toJson(QJsonDocument::Compact);
    auto *reply = manager.sendCustomRequest(
        makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/proposal-draft")), "PATCH", body);
    const auto responsePayload = waitForReply(reply, 5000, errorMessage);
    if (responsePayload.isNull()) {
        return {};
    }
    return parseCaseDetailResponse(responsePayload, errorMessage);
}

CaseDto CasesApi::createCaseFinalProposal(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.post(
        makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/final-proposal")), QByteArray());
    const auto responsePayload = waitForReply(reply, 5000, errorMessage);
    if (responsePayload.isNull()) {
        return {};
    }
    return parseCaseDetailResponse(responsePayload, errorMessage);
}
