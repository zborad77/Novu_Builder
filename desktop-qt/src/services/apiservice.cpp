#include "apiservice.h"

#include <QEventLoop>
#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

QString ApiService::s_bearerToken;
bool ApiService::s_sessionExpired = false;
QString ApiService::s_globalBaseUrl;

void ApiService::setGlobalToken(const QString &bearerToken)
{
    s_bearerToken = bearerToken;
    s_sessionExpired = false;
}

void ApiService::clearGlobalToken()
{
    s_bearerToken.clear();
}

bool ApiService::sessionExpired()
{
    return s_sessionExpired;
}

void ApiService::clearSessionExpired()
{
    s_sessionExpired = false;
}

void ApiService::markSessionExpired()
{
    s_sessionExpired = true;
    s_bearerToken.clear();
}

QNetworkRequest ApiService::makeAuthRequest(const QUrl &url) const
{
    QNetworkRequest request(url);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    if (!s_bearerToken.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + s_bearerToken.toUtf8());
    }
    return request;
}

LoginResultDto ApiService::login(const QString &email, const QString &password, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QJsonObject body;
    body["email"] = email;
    body["password"] = password;

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/auth/login"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.post(request, QJsonDocument(body).toJson(QJsonDocument::Compact));

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
        loop.quit();
    });
    timeoutTimer.start(8000);
    loop.exec();

    const auto httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (httpStatus == 0) {
        reply->deleteLater();
        if (errorMessage) {
            *errorMessage = "Backend neni dostupny. Zkontroluj zda bezi server.";
        }
        return {};
    }
    const auto responseData = reply->readAll();
    reply->deleteLater();

    const auto doc = QJsonDocument::fromJson(responseData);
    if (!doc.isObject()) {
        if (errorMessage) {
            *errorMessage = "Neplatna odpoved serveru.";
        }
        return {};
    }

    if (httpStatus != 200) {
        if (errorMessage) {
            const auto detail = doc.object().value("detail").toString();
            *errorMessage = detail.isEmpty() ? "Prihlaseni se nezdarilo." : detail;
        }
        return {};
    }

    const auto root = doc.object();
    const auto user = root.value("user").toObject();
    return LoginResultDto{
        .accessToken = root.value("accessToken").toString(),
        .refreshToken = root.value("refreshToken").toString(),
        .userId = user.value("id").toString(),
        .email = user.value("email").toString(),
        .fullName = user.value("fullName").toString(),
        .role = user.value("role").toString(),
        .isSuperAdmin = user.value("isSuperAdmin").toBool(),
    };
}

namespace {
QUrl resolveApiUrl(const QString &baseUrl, const QString &resourcePath)
{
    const QUrl candidate(resourcePath);
    if (candidate.isValid() && !candidate.scheme().isEmpty()) {
        return candidate;
    }

    QUrl rootUrl(baseUrl);
    rootUrl.setPath("/");
    rootUrl.setQuery(QString());
    rootUrl.setFragment(QString());
    return rootUrl.resolved(QUrl(resourcePath));
}

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
            label += QString(" \u2014 %1 %2").arg(qty, 0, 'f', 1).arg(unit);
        }
        if (hasQty && hasUnitPrice) {
            label += QString(" \u00D7 %1 CZK").arg(unitPrice, 0, 'f', 2);
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
                    label += " \u2014 " + desc;
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

std::vector<ImageDto> parseImageListResponse(const QByteArray &payload, QString *errorMessage)
{
    std::vector<ImageDto> result;

    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved pro images.";
        }
        return result;
    }

    const auto rootObject = document.object();
    const auto items = rootObject.value("items").toArray();

    result.reserve(static_cast<size_t>(items.size()));
    for (const auto &itemValue : items) {
        const auto itemObject = itemValue.toObject();
        const auto variants = itemObject.value("variants").toObject();
        const auto preview = variants.value("preview").toObject();

        QString dimensionsLabel;
        if (itemObject.value("width").isDouble() && itemObject.value("height").isDouble()) {
            dimensionsLabel = QString("%1 x %2")
                                  .arg(itemObject.value("width").toInt())
                                  .arg(itemObject.value("height").toInt());
        }

        result.push_back(
            {
                .id = itemObject.value("id").toString(),
                .originalFilename = itemObject.value("originalFilename").toString(),
                .previewUrl = preview.value("url").toString(),
                .dimensionsLabel = dimensionsLabel,
                .processingStatus = itemObject.value("processingStatus").toString(),
                .sortOrder = itemObject.value("sortOrder").toInt(),
                .isPrimary = itemObject.value("isPrimary").toBool(),
                .isAnalysisReference = itemObject.value("isAnalysisReference").toBool()
            }
        );
    }

    return result;
}

// ---------------------------------------------------------------------------
// Network reply helper — centralizes timeout, HTTP status, and 401 handling.
// Returns the raw body on success; sets *errorMessage and returns {} on error.
// Sets ApiService::s_sessionExpired=true and clears the token on HTTP 401.
// ---------------------------------------------------------------------------
QByteArray waitForReply(QNetworkReply *reply, int timeoutMs, QString *errorMessage)
{
    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    bool timedOut = false;

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]() {
        timedOut = true;
        if (reply->isRunning()) {
            reply->abort();
        }
        loop.quit();
    });

    timer.start(timeoutMs);
    loop.exec();

    const int httpStatus = reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();

    if (timedOut || reply->error() == QNetworkReply::OperationCanceledError) {
        reply->deleteLater();
        if (errorMessage) {
            *errorMessage = "Timeout — server neodpovida. Zkontroluj zda bezi backend.";
        }
        return {};
    }

    if (httpStatus == 401) {
        reply->deleteLater();
        ApiService::markSessionExpired();
        if (errorMessage) {
            *errorMessage = "Relace vyprsela. Prihlaste se znovu.";
        }
        return {};
    }

    if (reply->error() != QNetworkReply::NoError && httpStatus == 0) {
        const auto errStr = reply->errorString();
        reply->deleteLater();
        if (errorMessage) {
            *errorMessage = QString("Sit'ova chyba: %1").arg(errStr);
        }
        return {};
    }

    const QByteArray body = reply->readAll();
    reply->deleteLater();

    if (httpStatus >= 400) {
        if (errorMessage) {
            const auto doc = QJsonDocument::fromJson(body);
            const auto detail = doc.isObject() ? doc.object().value("detail").toString() : QString();
            *errorMessage = detail.isEmpty()
                ? QString("Chyba serveru (%1).").arg(httpStatus)
                : detail;
        }
        return {};
    }

    return body;
}

} // namespace

void ApiService::setGlobalBaseUrl(const QString &baseUrl)
{
    s_globalBaseUrl = baseUrl;
}

QString ApiService::globalBaseUrl()
{
    return s_globalBaseUrl.isEmpty() ? QStringLiteral("http://127.0.0.1:8000/api/v1") : s_globalBaseUrl;
}

ApiService::ApiService(QString baseUrl)
    : m_baseUrl(baseUrl.isEmpty() ? globalBaseUrl() : std::move(baseUrl))
{
}

QString ApiService::baseUrl() const
{
    return m_baseUrl;
}

std::vector<CaseDto> ApiService::fetchCases(QString *errorMessage) const
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

QString ApiService::createCase(
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
    if (ApiService::sessionExpired()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    return doc.object().value("id").toString();
}

QString ApiService::duplicateCase(const QString &caseId, const QString &mode, QString *errorMessage) const
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

bool ApiService::sendCase(const QString &caseId, QString *errorMessage) const
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

CaseDto ApiService::fetchCaseDetail(const QString &caseId, QString *errorMessage) const
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

CaseDto ApiService::updateCaseProposalDraft(
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

CaseDto ApiService::createCaseFinalProposal(const QString &caseId, QString *errorMessage) const
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

std::vector<ImageDto> ApiService::fetchCaseImages(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/images")));
    const auto payload = waitForReply(reply, 5000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return parseImageListResponse(payload, errorMessage);
}

std::vector<ImageDto> ApiService::moveCaseImage(
    const QString &caseId,
    const QString &imageId,
    const QString &direction,
    QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    const auto body = QJsonDocument(QJsonObject{{"direction", direction}}).toJson(QJsonDocument::Compact);
    auto *reply = manager.sendCustomRequest(
        makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/move")), "PATCH", body);
    const auto responsePayload = waitForReply(reply, 5000, errorMessage);
    if (responsePayload.isNull()) {
        return {};
    }
    return parseImageListResponse(responsePayload, errorMessage);
}

bool ApiService::setCasePrimaryImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.sendCustomRequest(
        makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/primary")), "PATCH");
    QString localError;
    const auto responsePayload = waitForReply(reply, 5000, &localError);
    if (responsePayload.isNull()) {
        if (errorMessage) *errorMessage = localError;
        return false;
    }
    return true;
}

bool ApiService::setCaseAnalysisReferenceImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    auto *reply = manager.sendCustomRequest(
        makeAuthRequest(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/analysis-reference")), "PATCH");
    QString localError;
    const auto responsePayload = waitForReply(reply, 5000, &localError);
    if (responsePayload.isNull()) {
        if (errorMessage) *errorMessage = localError;
        return false;
    }
    return true;
}

bool ApiService::uploadCaseImages(const QString &caseId, const std::vector<UploadImageDto> &images, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    if (images.empty()) {
        if (errorMessage) {
            *errorMessage = "Nejsou pripravene zadne fotky k odeslani.";
        }
        return false;
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/images"));
    if (!s_bearerToken.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + s_bearerToken.toUtf8());
    }

    auto *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    for (const auto &image : images) {
        QHttpPart imagePart;
        imagePart.setHeader(QNetworkRequest::ContentTypeHeader, image.mimeType);
        imagePart.setHeader(
            QNetworkRequest::ContentDispositionHeader,
            QString("form-data; name=\"files\"; filename=\"%1\"").arg(image.originalFilename));
        imagePart.setBody(image.payload);
        multiPart->append(imagePart);
    }

    auto *reply = manager.post(request, multiPart);
    multiPart->setParent(reply);

    QString localError;
    const auto responsePayload = waitForReply(reply, 15000, &localError);
    if (responsePayload.isNull()) {
        if (errorMessage) *errorMessage = localError;
        return false;
    }
    return true;
}

ExportDto ApiService::triggerExport(const QString &caseId, const QString &exportType, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    const auto triggerUrl = QUrl(m_baseUrl + "/cases/" + caseId + "/exports/" + exportType);
    auto *triggerReply = manager.post(makeAuthRequest(triggerUrl), QByteArray{});

    const auto triggerPayload = waitForReply(triggerReply, 15000, errorMessage);
    if (triggerPayload.isNull()) {
        return {};
    }

    const auto triggerDoc = QJsonDocument::fromJson(triggerPayload);
    const auto exportId = triggerDoc.object().value("exportId").toString();
    if (exportId.isEmpty()) {
        if (errorMessage) {
            *errorMessage = "Backend nevratil exportId.";
        }
        return {};
    }

    const auto statusUrl = QUrl(m_baseUrl + "/exports/" + exportId);
    auto *statusReply = manager.get(makeAuthRequest(statusUrl));

    const auto statusPayload = waitForReply(statusReply, 10000, errorMessage);
    if (statusPayload.isNull()) {
        return {};
    }

    const auto root = QJsonDocument::fromJson(statusPayload).object();
    return ExportDto{
        .id = root.value("id").toString(),
        .status = root.value("status").toString(),
        .downloadUrl = root.value("downloadUrl").toString(),
        .fileName = root.value("fileName").toString(),
    };
}

QByteArray ApiService::downloadExportFile(const QString &downloadUrl, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    if (downloadUrl.isEmpty()) {
        if (errorMessage) {
            *errorMessage = "Download URL chybi.";
        }
        return {};
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(resolveApiUrl(m_baseUrl, downloadUrl));
    if (!s_bearerToken.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + s_bearerToken.toUtf8());
    }
    auto *reply = manager.get(request);

    const auto payload = waitForReply(reply, 15000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return payload;
}

QString ApiService::triggerAnalysisJob(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QNetworkAccessManager manager;
    const auto url = QUrl(QString("%1/cases/%2/analysis-jobs").arg(m_baseUrl, caseId));
    auto *reply = manager.post(makeAuthRequest(url), QByteArray("{}"));

    const auto response = waitForReply(reply, 20000, errorMessage);
    if (response.isNull()) return {};

    const auto obj = QJsonDocument::fromJson(response).object();
    const auto jobId = obj.value("jobId").toString();
    if (jobId.isEmpty()) {
        if (errorMessage) *errorMessage = "Server nevrátil jobId.";
    }
    return jobId;
}

QString ApiService::getAnalysisJobStatus(const QString &jobId, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QNetworkAccessManager manager;
    const auto url = QUrl(QString("%1/analysis-jobs/%2").arg(m_baseUrl, jobId));
    auto *reply = manager.get(makeAuthRequest(url));

    const auto response = waitForReply(reply, 6000, errorMessage);
    if (response.isNull()) return {};

    return QJsonDocument::fromJson(response).object().value("status").toString();
}

bool ApiService::patchAnalysisSelection(
    const QString &caseId,
    const QString &analysisResultId,
    const QVector<QPointF> &polygon,
    double manualAreaSqm,
    QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QJsonArray polygonArray;
    for (const auto &pt : polygon) {
        polygonArray.append(QJsonObject{{"x", pt.x()}, {"y", pt.y()}});
    }
    QJsonObject bodyObj{{"polygon", polygonArray}};
    if (manualAreaSqm > 0.0) {
        bodyObj["manualAreaSqm"] = manualAreaSqm;
    }
    const auto body = QJsonDocument(bodyObj).toJson(QJsonDocument::Compact);

    QNetworkAccessManager manager;
    const auto url = QUrl(QString("%1/cases/%2/analysis-results/%3/selection")
        .arg(m_baseUrl, caseId, analysisResultId));
    auto *reply = manager.sendCustomRequest(makeAuthRequest(url), "PATCH", body);
    const auto response = waitForReply(reply, 8000, errorMessage);
    if (response.isNull()) return false;
    if (ApiService::sessionExpired()) return false;

    const auto obj = QJsonDocument::fromJson(response).object();
    return obj.value("status").toString() == "ok";
}

QByteArray ApiService::fetchImageData(const QString &imageUrl, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    if (imageUrl.isEmpty()) {
        if (errorMessage) {
            *errorMessage = "Preview URL chybi.";
        }
        return {};
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(resolveApiUrl(m_baseUrl, imageUrl));
    if (!s_bearerToken.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + s_bearerToken.toUtf8());
    }

    auto *reply = manager.get(request);

    const auto payload = waitForReply(reply, 5000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return payload;
}

// ── Admin API ─────────────────────────────────────────────────────────────────

std::vector<AdminUserDto> ApiService::fetchAdminUsers(const QString &orgId, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QString path = "/api/v1/admin/users";
    if (!orgId.isEmpty()) {
        path += "?org_id=" + QString::fromUtf8(QUrl::toPercentEncoding(orgId));
    }

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + path)));
    const auto payload = waitForReply(reply, 8000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    std::vector<AdminUserDto> result;
    const auto items = doc.object().value("items").toArray();
    for (const auto &item : items) {
        const auto obj = item.toObject();
        AdminUserDto u;
        u.id = obj.value("id").toString();
        u.orgId = obj.value("organizationId").toString();
        u.orgName = obj.value("organizationName").toString();
        u.email = obj.value("email").toString();
        u.fullName = obj.value("fullName").toString();
        u.role = obj.value("role").toString();
        u.isActive = obj.value("isActive").toBool(true);
        u.isSuperAdmin = obj.value("isSuperAdmin").toBool(false);
        result.push_back(u);
    }
    return result;
}

bool ApiService::resetUserPassword(const QString &userId, const QString &newPassword, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QJsonObject body;
    body["password"] = newPassword;

    QNetworkAccessManager manager;
    const QUrl url(m_baseUrl + "/api/v1/admin/users/" + userId + "/reset-password");
    auto *reply = manager.post(makeAuthRequest(url), QJsonDocument(body).toJson(QJsonDocument::Compact));
    const auto payload = waitForReply(reply, 8000, errorMessage);

    // 204 No Content = success (payload empty, no error set)
    if (errorMessage && !errorMessage->isEmpty()) return false;
    if (payload.isEmpty()) return true;

    const auto doc = QJsonDocument::fromJson(payload);
    if (errorMessage) {
        *errorMessage = doc.object().value("detail").toString(QString::fromUtf8("Reset hesla selhal."));
    }
    return false;
}

std::vector<AdminJobDto> ApiService::fetchAdminJobs(const QString &statusFilter, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QString path = "/api/v1/admin/jobs";
    if (!statusFilter.isEmpty()) {
        path += "?status=" + QString::fromUtf8(QUrl::toPercentEncoding(statusFilter));
    }

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + path)));
    const auto payload = waitForReply(reply, 8000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isArray()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    std::vector<AdminJobDto> result;
    for (const auto &item : doc.array()) {
        const auto obj = item.toObject();
        AdminJobDto j;
        j.id = obj.value("id").toString();
        j.caseId = obj.value("caseId").toString();
        j.caseTitle = obj.value("caseTitle").toString();
        j.orgId = obj.value("orgId").toString();
        j.orgName = obj.value("orgName").toString();
        j.status = obj.value("status").toString();
        j.jobType = obj.value("jobType").toString();
        j.startedAt = obj.value("startedAt").toString();
        j.finishedAt = obj.value("finishedAt").toString();
        j.errorMessage = obj.value("errorMessage").toString();
        j.createdAt = obj.value("createdAt").toString();
        result.push_back(j);
    }
    return result;
}

QString ApiService::fetchAdminLogs(int lines, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    const QString path = QString("/api/v1/admin/logs?lines=%1").arg(lines);

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + path)));
    const auto payload = waitForReply(reply, 10000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isArray()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    QStringList linesList;
    for (const auto &item : doc.array()) {
        linesList.append(item.toString());
    }
    return linesList.join('\n');
}
