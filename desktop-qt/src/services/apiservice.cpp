#include "apiservice.h"

#include "sessionservice.h"

#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QTimer>
#include <QUrl>

QString ApiService::s_globalBaseUrl;

// ── Static session management ─────────────────────────────────────────────────

void ApiService::setGlobalBaseUrl(const QString &url)
{
    QString normalized = url.trimmed();
    while (normalized.endsWith('/'))
        normalized.chop(1);
    s_globalBaseUrl = normalized;
}

QString ApiService::globalBaseUrl()
{
    return s_globalBaseUrl;
}

// ── Constructor ───────────────────────────────────────────────────────────────

ApiService::ApiService(SessionService &session, QObject *parent)
    : QObject(parent)
    , m_nam(new QNetworkAccessManager(this))
    , m_session(&session)
{
}

// ── URL helpers ───────────────────────────────────────────────────────────────

QUrl ApiService::urlFor(const QString &path) const
{
    return QUrl(s_globalBaseUrl + path);
}

QUrl ApiService::resolveAbsolute(const QString &urlOrPath) const
{
    const QUrl candidate(urlOrPath);
    if (candidate.isValid() && !candidate.scheme().isEmpty())
        return candidate;
    QUrl root(s_globalBaseUrl);
    root.setPath("/");
    root.setQuery(QString());
    root.setFragment(QString());
    return root.resolved(QUrl(urlOrPath));
}

QNetworkRequest ApiService::makeAuthRequest(const QUrl &url) const
{
    QNetworkRequest req(url);
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    const QString token = bearerToken();
    if (!token.isEmpty())
        req.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
    return req;
}

QString ApiService::bearerToken() const
{
    return m_session ? m_session->token() : QString();
}

// ── Core async helper ─────────────────────────────────────────────────────────

void ApiService::watchReply(QNetworkReply *reply,
                              int timeoutMs,
                              std::function<void(QByteArray, QString)> callback,
                              bool notifySessionExpiry)
{
    auto *timer = new QTimer(reply);
    timer->setSingleShot(true);
    connect(timer, &QTimer::timeout, reply, &QNetworkReply::abort);
    timer->start(timeoutMs);

    connect(reply, &QNetworkReply::finished, this,
            [this, reply, cb = std::move(callback), notifySessionExpiry]() mutable {
                reply->deleteLater();

                const int status =
                    reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();

                if (reply->error() == QNetworkReply::OperationCanceledError) {
                    cb({}, QStringLiteral(
                               "Timeout - server neodpovida. Zkontroluj zda bezi backend."));
                    return;
                }

                if (reply->error() != QNetworkReply::NoError && status == 0) {
                    cb({}, QStringLiteral("Sitova chyba: %1").arg(reply->errorString()));
                    return;
                }

                if (status == 401) {
                    if (notifySessionExpiry) {
                        if (m_session)
                            m_session->markSessionExpired();
                        emit sessionExpired();
                        cb({}, QStringLiteral("Relace vyprsela. Prihlaste se znovu."));
                    } else {
                        const auto doc = QJsonDocument::fromJson(reply->readAll());
                        const auto detail =
                            doc.isObject() ? doc.object().value("detail").toString() : QString();
                        cb({}, detail.isEmpty()
                                   ? QStringLiteral("Prihlaseni se nezdarilo.")
                                   : detail);
                    }
                    return;
                }

                const QByteArray body = reply->readAll();

                if (status >= 400) {
                    const auto doc = QJsonDocument::fromJson(body);
                    const auto detail =
                        doc.isObject() ? doc.object().value("detail").toString() : QString();
                    cb({}, detail.isEmpty() ? QString("Chyba serveru (%1).").arg(status) : detail);
                    return;
                }

                cb(body, {});
            });
}

// ── Parsers (free functions, internal) ────────────────────────────────────────

namespace {

QString jsonTypeName(const QJsonValue &value)
{
    switch (value.type()) {
    case QJsonValue::Null:
        return "null";
    case QJsonValue::Bool:
        return "bool";
    case QJsonValue::Double:
        return "number";
    case QJsonValue::String:
        return "string";
    case QJsonValue::Array:
        return "array";
    case QJsonValue::Object:
        return "object";
    case QJsonValue::Undefined:
        return "undefined";
    }
    return "unknown";
}

QString jsonRootTypeName(const QJsonDocument &doc)
{
    if (doc.isArray()) {
        return "array";
    }
    if (doc.isObject()) {
        return "object";
    }
    if (doc.isNull()) {
        return "null";
    }
    return "invalid";
}

bool parseJsonDocument(const QByteArray &body,
                       const QString &context,
                       QJsonDocument *outDoc,
                       QString *outError)
{
    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(body, &parseError);
    if (parseError.error != QJsonParseError::NoError || doc.isNull()) {
        if (outError) {
            *outError = QString("%1: neplatny JSON (%2).")
                            .arg(context, parseError.errorString());
        }
        return false;
    }

    if (outDoc) {
        *outDoc = doc;
    }
    if (outError) {
        outError->clear();
    }
    return true;
}

bool parseRootArray(const QByteArray &body,
                    const QString &context,
                    QJsonArray *outArray,
                    QString *outError)
{
    QJsonDocument doc;
    if (!parseJsonDocument(body, context, &doc, outError)) {
        return false;
    }
    if (!doc.isArray()) {
        if (outError) {
            *outError = QString("%1: ocekavan root array, prisel %2.")
                            .arg(context, jsonRootTypeName(doc));
        }
        return false;
    }

    if (outArray) {
        *outArray = doc.array();
    }
    if (outError) {
        outError->clear();
    }
    return true;
}

bool parseObjectArrayField(const QByteArray &body,
                           const QString &context,
                           const QString &fieldName,
                           QJsonArray *outArray,
                           QString *outError)
{
    QJsonDocument doc;
    if (!parseJsonDocument(body, context, &doc, outError)) {
        return false;
    }
    if (!doc.isObject()) {
        if (outError) {
            *outError = QString("%1: ocekavan root object, prisel %2.")
                            .arg(context, jsonRootTypeName(doc));
        }
        return false;
    }

    const QJsonObject root = doc.object();
    const QJsonValue field = root.value(fieldName);
    if (!field.isArray()) {
        if (outError) {
            *outError = QString("%1: pole '%2' musi byt array, ale je %3.")
                            .arg(context, fieldName, jsonTypeName(field));
        }
        return false;
    }

    if (outArray) {
        *outArray = field.toArray();
    }
    if (outError) {
        outError->clear();
    }
    return true;
}

QString formatCurrencyLabel(const QJsonValue &v)
{
    if (!v.isDouble())
        return {};
    return QString::number(v.toDouble(), 'f', 2) + " CZK";
}

CaseDto parseCaseDetail(const QByteArray &payload)
{
    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject())
        return {};

    const auto root = doc.object();
    const auto location = root.value("location").toObject();
    const auto latestAnalysis = root.value("latestAnalysis").toObject();
    const auto proposalDraft = root.value("proposalDraft").toObject();
    const auto finalProposal = root.value("finalProposal").toObject();
    const auto workflowStatus = root.value("workflowStatus").toObject();
    const auto blockingReasons = workflowStatus.value("blockingReasons").toArray();
    const auto referenceExpectations = root.value("referenceExpectations").toObject();
    const auto suggestedWorkItems = proposalDraft.value("suggestedWorkItems").toArray();
    const auto materials = proposalDraft.value("materials").toArray();

    QString areaLabel;
    const auto manualArea = latestAnalysis.value("manualAreaSqm");
    const auto estimatedArea = latestAnalysis.value("estimatedAreaSqm");
    if (manualArea.isDouble())
        areaLabel = QString::number(manualArea.toDouble(), 'f', 1) + " m2 manual";
    else if (estimatedArea.isDouble())
        areaLabel = QString::number(estimatedArea.toDouble(), 'f', 1) + " m2 AI";

    QStringList proposalWorkItems;
    for (const auto &v : suggestedWorkItems) {
        const auto obj = v.toObject();
        QString label = obj.value("name").toString();
        const auto note = obj.value("note").toString();
        if (!note.isEmpty())
            label += " - " + note;
        if (!label.isEmpty())
            proposalWorkItems.push_back(label);
    }

    QStringList proposalMaterials;
    QList<CaseDto::ProposalMaterialItem> proposalMaterialItems;
    for (const auto &v : materials) {
        const auto obj = v.toObject();
        const QString name = obj.value("name").toString();
        const double qty = obj.value("quantity").toDouble();
        const QString unit = obj.value("unit").toString();
        const double unitPrice = obj.value("unitPrice").toDouble();
        const double totalPrice = obj.value("totalPrice").toDouble();
        const bool hasQty = obj.value("quantity").isDouble() && !unit.isEmpty();
        const bool hasUnitPrice = obj.value("unitPrice").isDouble();
        const bool hasTotalPrice = obj.value("totalPrice").isDouble();
        proposalMaterialItems.push_back({name, qty, unit, unitPrice, totalPrice});
        QString label = name;
        if (hasQty)
            label += QString(" - %1 %2").arg(qty, 0, 'f', 1).arg(unit);
        if (hasQty && hasUnitPrice)
            label += QString(" x %1 CZK").arg(unitPrice, 0, 'f', 2);
        if (hasTotalPrice)
            label += QString(" = %1 CZK").arg(totalPrice, 0, 'f', 2);
        if (!label.isEmpty())
            proposalMaterials.push_back(label);
    }

    QStringList workflowBlockingReasons;
    for (const auto &v : blockingReasons) {
        const auto r = v.toString().trimmed();
        if (!r.isEmpty())
            workflowBlockingReasons.push_back(r);
    }

    const bool hasAnalysis =
        !latestAnalysis.isEmpty() && !latestAnalysis.value("id").toString().isEmpty();
    QStringList analysisWorkflowSteps, analysisMaterialItems;
    QVector<QPointF> analysisMaskPolygon;
    if (hasAnalysis) {
        for (const auto &pt : latestAnalysis.value("maskPolygon").toArray()) {
            const auto obj = pt.toObject();
            analysisMaskPolygon.append({obj.value("x").toDouble(), obj.value("y").toDouble()});
        }
        int autoIndex = 1;
        for (const auto &sv : latestAnalysis.value("workflowSteps").toArray()) {
            QString label;
            if (sv.isString()) {
                label = QString("%1. %2").arg(autoIndex).arg(sv.toString());
            } else {
                const auto step = sv.toObject();
                const int num = step.value("step").toInt(autoIndex);
                const QString name = step.value("name").toString();
                const double hours = step.value("estimatedHours").toDouble();
                label = QString("%1. %2").arg(num).arg(name);
                if (hours > 0)
                    label += QString(" (%1 h)").arg(hours, 0, 'f', 1);
                const QString desc = step.value("description").toString();
                if (!desc.isEmpty())
                    label += " - " + desc;
            }
            if (!label.isEmpty())
                analysisWorkflowSteps.push_back(label);
            ++autoIndex;
        }
        for (const auto &mv : latestAnalysis.value("materials").toArray()) {
            const auto mat = mv.toObject();
            QString label = mat.value("name").toString();
            const bool hasQty =
                mat.value("quantity").isDouble() && !mat.value("unit").toString().isEmpty();
            if (hasQty)
                label += QString(" - %1 %2")
                             .arg(mat.value("quantity").toDouble(), 0, 'f', 1)
                             .arg(mat.value("unit").toString());
            if (hasQty && mat.value("unitPrice").isDouble())
                label += QString(" x %1 CZK").arg(mat.value("unitPrice").toDouble(), 0, 'f', 2);
            if (mat.value("totalPrice").isDouble())
                label += QString(" = %1 CZK").arg(mat.value("totalPrice").toDouble(), 0, 'f', 2);
            if (!label.isEmpty())
                analysisMaterialItems.push_back(label);
        }
    }

    const auto quoteVariantsArray = root.value("quoteVariants").toArray();
    QString quoteEconomyLabel, quoteStandardLabel, quotePremiumLabel;
    double quoteEconomyTotal = 0, quoteStandardTotal = 0, quotePremiumTotal = 0;
    for (const auto &vv : quoteVariantsArray) {
        const auto variant = vv.toObject();
        const QString vtype = variant.value("variantType").toString();
        const double total = variant.value("totalIncVat").toDouble();
        const double labor = variant.value("laborCost").toDouble();
        const double material = variant.value("materialCost").toDouble();
        const QString label = QString("%1 CZK (prace %2 + mat. %3)")
                                  .arg(total, 0, 'f', 0)
                                  .arg(labor, 0, 'f', 0)
                                  .arg(material, 0, 'f', 0);
        if (vtype == "economy") { quoteEconomyLabel = label; quoteEconomyTotal = total; }
        else if (vtype == "standard") { quoteStandardLabel = label; quoteStandardTotal = total; }
        else if (vtype == "premium") { quotePremiumLabel = label; quotePremiumTotal = total; }
    }

    return {
        .id = root.value("id").toString(),
        .title = root.value("title").toString(),
        .status = root.value("status").toString(),
        .isReferenceDataset = root.value("isReferenceDataset").toBool(),
        .source = root.value("source").toString("mobile"),
        .addressLabel = location.value("addressLabel").toString(),
        .description = root.value("description").toString(),
        .propertyType = root.value("propertyType").toString(),
        .repairScope = root.value("repairScope").toString(),
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
        .expectedAnalysisReferenceFilename =
            referenceExpectations.value("expectedAnalysisReferenceFilename").toString(),
        .referenceSourcePage = referenceExpectations.value("sourcePage").toString(),
        .finalProposalStatus = finalProposal.value("status").toString(),
        .workflowFinalProposalStatus = workflowStatus.value("finalProposalStatus").toString(),
        .finalProposalDraftVersionLabel =
            finalProposal.value("draftVersion").isDouble()
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
        .hasQuoteVariants = !quoteVariantsArray.isEmpty(),
        .quoteEconomyLabel = quoteEconomyLabel,
        .quoteStandardLabel = quoteStandardLabel,
        .quotePremiumLabel = quotePremiumLabel,
        .quoteEconomyTotalIncVat = quoteEconomyTotal,
        .quoteStandardTotalIncVat = quoteStandardTotal,
        .quotePremiumTotalIncVat = quotePremiumTotal,
    };
}

std::vector<CaseDto> parseCaseList(const QByteArray &payload)
{
    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject())
        return {};

    std::vector<CaseDto> result;
    for (const auto &v : doc.object().value("items").toArray()) {
        const auto obj = v.toObject();
        result.push_back({
            .id = obj.value("id").toString(),
            .title = obj.value("title").toString(),
            .status = obj.value("status").toString(),
            .isReferenceDataset = obj.value("isReferenceDataset").toBool(),
            .addressLabel = obj.value("addressLabel").toString(),
            .createdByName = obj.value("createdByName").toString(),
            .propertyType = obj.value("propertyType").toString(),
            .repairScope = obj.value("repairScope").toString(),
            .areaLabel = obj.value("estimatedAreaSqm").isDouble()
                             ? QString::number(obj.value("estimatedAreaSqm").toDouble(), 'f', 1) +
                                   " m2"
                             : QString(),
        });
    }
    return result;
}

std::vector<ImageDto> parseImageList(const QByteArray &payload)
{
    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject())
        return {};

    std::vector<ImageDto> result;
    for (const auto &v : doc.object().value("items").toArray()) {
        const auto obj = v.toObject();
        const auto preview = obj.value("variants").toObject().value("preview").toObject();
        QString dimensionsLabel;
        if (obj.value("width").isDouble() && obj.value("height").isDouble())
            dimensionsLabel =
                QString("%1 x %2").arg(obj.value("width").toInt()).arg(obj.value("height").toInt());
        result.push_back({
            .id = obj.value("id").toString(),
            .originalFilename = obj.value("originalFilename").toString(),
            .previewUrl = preview.value("url").toString(),
            .dimensionsLabel = dimensionsLabel,
            .processingStatus = obj.value("processingStatus").toString(),
            .sortOrder = obj.value("sortOrder").toInt(),
            .isPrimary = obj.value("isPrimary").toBool(),
            .isAnalysisReference = obj.value("isAnalysisReference").toBool(),
        });
    }
    return result;
}

} // namespace

// ── Auth ──────────────────────────────────────────────────────────────────────

void ApiService::login(const QString &email,
                        const QString &password,
                        std::function<void(LoginResultDto)> onSuccess,
                        std::function<void(QString)> onError)
{
    QJsonObject body;
    body["email"] = email;
    body["password"] = password;

    QNetworkRequest req(QUrl(s_globalBaseUrl + "/auth/login"));
    req.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = m_nam->post(req, QJsonDocument(body).toJson(QJsonDocument::Compact));
    watchReply(reply, 8000,
               [onSuccess, onError](QByteArray body, QString err) {
                   if (!err.isEmpty()) {
                       if (onError) onError(err);
                       return;
                   }
                   const auto root = QJsonDocument::fromJson(body).object();
                   const auto user = root.value("user").toObject();
                   if (onSuccess)
                       onSuccess(LoginResultDto{
                           .accessToken = root.value("accessToken").toString(),
                           .refreshToken = root.value("refreshToken").toString(),
                           .userId = user.value("id").toString(),
                           .email = user.value("email").toString(),
                           .fullName = user.value("fullName").toString(),
                           .role = user.value("role").toString(),
                           .isSuperAdmin = user.value("isSuperAdmin").toBool(),
                       });
               },
               false /* 401 = wrong credentials, not session expiry */);
}

// ── Cases ─────────────────────────────────────────────────────────────────────

void ApiService::fetchCases(std::function<void(std::vector<CaseDto>)> onSuccess,
                              std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(makeAuthRequest(urlFor("/cases")));
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseCaseList(body));
    });
}

void ApiService::fetchCaseDetail(const QString &caseId,
                                  std::function<void(CaseDto)> onSuccess,
                                  std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(makeAuthRequest(urlFor("/cases/" + caseId)));
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseCaseDetail(body));
    });
}

void ApiService::createCase(const QString &title,
                             const QString &addressLabel,
                             const QString &repairScope,
                             const QString &description,
                             std::function<void(QString)> onSuccess,
                             std::function<void(QString)> onError)
{
    QJsonObject body;
    body["title"] = title;
    body["source"] = QStringLiteral("desktop");
    if (!addressLabel.isEmpty()) body["addressLabel"] = addressLabel;
    if (!repairScope.isEmpty()) body["repairScope"] = repairScope;
    if (!description.isEmpty()) body["description"] = description;

    auto *reply = m_nam->post(makeAuthRequest(urlFor("/cases")),
                               QJsonDocument(body).toJson(QJsonDocument::Compact));
    watchReply(reply, 10000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto id = QJsonDocument::fromJson(body).object().value("id").toString();
        if (onSuccess) onSuccess(id);
    });
}

void ApiService::duplicateCase(const QString &caseId,
                                const QString &mode,
                                std::function<void(QString)> onSuccess,
                                std::function<void(QString)> onError)
{
    const auto body =
        QJsonDocument(QJsonObject{{"mode", mode}}).toJson(QJsonDocument::Compact);
    auto *reply = m_nam->post(makeAuthRequest(urlFor("/cases/" + caseId + "/duplicate")), body);
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto id = QJsonDocument::fromJson(body).object().value("id").toString();
        if (onSuccess) onSuccess(id);
    });
}

void ApiService::sendCase(const QString &caseId,
                           std::function<void()> onSuccess,
                           std::function<void(QString)> onError)
{
    auto *reply =
        m_nam->post(makeAuthRequest(urlFor("/cases/" + caseId + "/send")), QByteArray());
    watchReply(reply, 5000, [onSuccess, onError](QByteArray, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess();
    });
}

void ApiService::updateCaseProposalDraft(const QString &caseId,
                                          const ProposalDraftPatchDto &draft,
                                          std::function<void(CaseDto)> onSuccess,
                                          std::function<void(QString)> onError)
{
    const auto body = QJsonDocument(QJsonObject{
                                        {"subject", draft.subject},
                                        {"summary", draft.summary},
                                        {"materialCost", draft.materialCost},
                                        {"laborCost", draft.laborCost},
                                        {"transportCost", draft.transportCost},
                                        {"amortization", draft.amortization},
                                        {"margin", draft.margin},
                                        {"recommendedSupplier", draft.recommendedSupplier},
                                        {"recommendedCompany", draft.recommendedCompany},
                                    })
                          .toJson(QJsonDocument::Compact);
    auto *reply = m_nam->sendCustomRequest(
        makeAuthRequest(urlFor("/cases/" + caseId + "/proposal-draft")), "PATCH", body);
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseCaseDetail(body));
    });
}

void ApiService::createCaseFinalProposal(const QString &caseId,
                                          std::function<void(CaseDto)> onSuccess,
                                          std::function<void(QString)> onError)
{
    auto *reply = m_nam->post(
        makeAuthRequest(urlFor("/cases/" + caseId + "/final-proposal")), QByteArray());
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseCaseDetail(body));
    });
}

// ── Images ────────────────────────────────────────────────────────────────────

void ApiService::fetchCaseImages(const QString &caseId,
                                  std::function<void(std::vector<ImageDto>)> onSuccess,
                                  std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(makeAuthRequest(urlFor("/cases/" + caseId + "/images")));
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseImageList(body));
    });
}

void ApiService::moveCaseImage(const QString &caseId,
                                const QString &imageId,
                                const QString &direction,
                                std::function<void(std::vector<ImageDto>)> onSuccess,
                                std::function<void(QString)> onError)
{
    const auto body =
        QJsonDocument(QJsonObject{{"direction", direction}}).toJson(QJsonDocument::Compact);
    auto *reply = m_nam->sendCustomRequest(
        makeAuthRequest(urlFor("/cases/" + caseId + "/images/" + imageId + "/move")), "PATCH",
        body);
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(parseImageList(body));
    });
}

void ApiService::setCasePrimaryImage(const QString &caseId,
                                      const QString &imageId,
                                      std::function<void()> onSuccess,
                                      std::function<void(QString)> onError)
{
    auto *reply = m_nam->sendCustomRequest(
        makeAuthRequest(urlFor("/cases/" + caseId + "/images/" + imageId + "/primary")), "PATCH");
    watchReply(reply, 5000, [onSuccess, onError](QByteArray, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess();
    });
}

void ApiService::setCaseAnalysisReferenceImage(const QString &caseId,
                                                const QString &imageId,
                                                std::function<void()> onSuccess,
                                                std::function<void(QString)> onError)
{
    auto *reply = m_nam->sendCustomRequest(
        makeAuthRequest(
            urlFor("/cases/" + caseId + "/images/" + imageId + "/analysis-reference")),
        "PATCH");
    watchReply(reply, 5000, [onSuccess, onError](QByteArray, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess();
    });
}

void ApiService::uploadCaseImages(const QString &caseId,
                                   const std::vector<UploadImageDto> &images,
                                   std::function<void()> onSuccess,
                                   std::function<void(QString)> onError)
{
    if (images.empty()) {
        if (onError) onError(QStringLiteral("Nejsou pripraveny zadne fotky k odeslani."));
        return;
    }

    QNetworkRequest req(urlFor("/cases/" + caseId + "/images"));
    const QString token = bearerToken();
    if (!token.isEmpty())
        req.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());

    auto *multiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);
    for (const auto &img : images) {
        QHttpPart part;
        part.setHeader(QNetworkRequest::ContentTypeHeader, img.mimeType);
        part.setHeader(QNetworkRequest::ContentDispositionHeader,
                       QString("form-data; name=\"files\"; filename=\"%1\"")
                           .arg(img.originalFilename));
        part.setBody(img.payload);
        multiPart->append(part);
    }

    auto *reply = m_nam->post(req, multiPart);
    multiPart->setParent(reply);

    watchReply(reply, 30000, [onSuccess, onError](QByteArray, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess();
    });
}

void ApiService::fetchImageData(const QString &imageUrl,
                                 std::function<void(QByteArray)> onSuccess,
                                 std::function<void(QString)> onError)
{
    QNetworkRequest req(resolveAbsolute(imageUrl));
    const QString token = bearerToken();
    if (!token.isEmpty())
        req.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
    auto *reply = m_nam->get(req);
    watchReply(reply, 5000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(body);
    });
}

// ── Analysis ──────────────────────────────────────────────────────────────────

void ApiService::triggerAnalysisJob(const QString &caseId,
                                     std::function<void(QString)> onSuccess,
                                     std::function<void(QString)> onError)
{
    auto *reply =
        m_nam->post(makeAuthRequest(urlFor("/cases/" + caseId + "/analysis-jobs")),
                    QByteArray("{}"));
    watchReply(reply, 20000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto jobId =
            QJsonDocument::fromJson(body).object().value("jobId").toString();
        if (onSuccess) onSuccess(jobId);
    });
}

void ApiService::getAnalysisJobStatus(const QString &jobId,
                                       std::function<void(QString)> onSuccess,
                                       std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(makeAuthRequest(urlFor("/analysis-jobs/" + jobId)));
    watchReply(reply, 6000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto status =
            QJsonDocument::fromJson(body).object().value("status").toString();
        if (onSuccess) onSuccess(status);
    });
}

void ApiService::patchAnalysisSelection(const QString &caseId,
                                         const QString &analysisResultId,
                                         const QVector<QPointF> &polygon,
                                         double manualAreaSqm,
                                         std::function<void()> onSuccess,
                                         std::function<void(QString)> onError)
{
    QJsonArray polygonArray;
    for (const auto &pt : polygon)
        polygonArray.append(QJsonObject{{"x", pt.x()}, {"y", pt.y()}});
    QJsonObject bodyObj{{"polygon", polygonArray}};
    if (manualAreaSqm > 0.0)
        bodyObj["manualAreaSqm"] = manualAreaSqm;

    auto *reply = m_nam->sendCustomRequest(
        makeAuthRequest(urlFor("/cases/" + caseId + "/analysis-results/" + analysisResultId +
                               "/selection")),
        "PATCH", QJsonDocument(bodyObj).toJson(QJsonDocument::Compact));
    watchReply(reply, 8000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto status =
            QJsonDocument::fromJson(body).object().value("status").toString();
        if (status == "ok") { if (onSuccess) onSuccess(); }
        else { if (onError) onError("Unexpected status from server."); }
    });
}

// ── Exports ───────────────────────────────────────────────────────────────────

void ApiService::triggerExport(const QString &caseId,
                                const QString &exportType,
                                std::function<void(ExportDto)> onSuccess,
                                std::function<void(QString)> onError)
{
    auto *triggerReply =
        m_nam->post(makeAuthRequest(urlFor("/cases/" + caseId + "/exports/" + exportType)),
                    QByteArray{});
    watchReply(triggerReply, 15000,
               [this, onSuccess, onError](QByteArray body, QString err) mutable {
                   if (!err.isEmpty()) { if (onError) onError(err); return; }
                   const auto exportId =
                       QJsonDocument::fromJson(body).object().value("exportId").toString();
                   if (exportId.isEmpty()) {
                       if (onError) onError("Backend nevratil exportId.");
                       return;
                   }
                   auto *statusReply =
                       m_nam->get(makeAuthRequest(urlFor("/exports/" + exportId)));
                   watchReply(statusReply, 10000,
                              [onSuccess, onError](QByteArray body, QString err) {
                                  if (!err.isEmpty()) { if (onError) onError(err); return; }
                                  const auto obj = QJsonDocument::fromJson(body).object();
                                  if (onSuccess)
                                      onSuccess(ExportDto{
                                          .id = obj.value("id").toString(),
                                          .status = obj.value("status").toString(),
                                          .downloadUrl = obj.value("downloadUrl").toString(),
                                          .fileName = obj.value("fileName").toString(),
                                      });
                              });
               });
}

void ApiService::downloadExportFile(const QString &downloadUrl,
                                     std::function<void(QByteArray)> onSuccess,
                                     std::function<void(QString)> onError)
{
    QNetworkRequest req(resolveAbsolute(downloadUrl));
    const QString token = bearerToken();
    if (!token.isEmpty())
        req.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
    auto *reply = m_nam->get(req);
    watchReply(reply, 15000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess(body);
    });
}

// ── Admin ─────────────────────────────────────────────────────────────────────

void ApiService::fetchAdminUsers(const QString &orgId,
                                  std::function<void(std::vector<AdminUserDto>)> onSuccess,
                                  std::function<void(QString)> onError)
{
    QString path = "/api/v1/admin/users";
    if (!orgId.isEmpty())
        path += "?org_id=" + QString::fromUtf8(QUrl::toPercentEncoding(orgId));
    auto *reply = m_nam->get(makeAuthRequest(urlFor(path)));
    watchReply(reply, 8000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        QJsonArray items;
        QString parseError;
        if (!parseObjectArrayField(body, "Admin users response", "items", &items, &parseError)) {
            if (onError) onError(parseError);
            return;
        }
        std::vector<AdminUserDto> result;
        for (const auto &v : items) {
            const auto obj = v.toObject();
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
        if (onSuccess) onSuccess(result);
    });
}

void ApiService::resetUserPassword(const QString &userId,
                                    const QString &newPassword,
                                    std::function<void()> onSuccess,
                                    std::function<void(QString)> onError)
{
    const auto body =
        QJsonDocument(QJsonObject{{"password", newPassword}}).toJson(QJsonDocument::Compact);
    auto *reply = m_nam->post(
        makeAuthRequest(urlFor("/api/v1/admin/users/" + userId + "/reset-password")), body);
    watchReply(reply, 8000, [onSuccess, onError](QByteArray, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        if (onSuccess) onSuccess();
    });
}

void ApiService::fetchAdminJobs(const QString &statusFilter,
                                 std::function<void(std::vector<AdminJobDto>)> onSuccess,
                                 std::function<void(QString)> onError)
{
    QString path = "/api/v1/admin/jobs";
    if (!statusFilter.isEmpty())
        path += "?status=" + QString::fromUtf8(QUrl::toPercentEncoding(statusFilter));
    auto *reply = m_nam->get(makeAuthRequest(urlFor(path)));
    watchReply(reply, 8000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        QJsonArray jobs;
        QString parseError;
        if (!parseRootArray(body, "Admin jobs response", &jobs, &parseError)) {
            if (onError) onError(parseError);
            return;
        }
        std::vector<AdminJobDto> result;
        for (const auto &v : jobs) {
            const auto obj = v.toObject();
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
        if (onSuccess) onSuccess(result);
    });
}

void ApiService::fetchAdminLogs(int lines,
                                 std::function<void(QString)> onSuccess,
                                 std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(
        makeAuthRequest(urlFor(QString("/api/v1/admin/logs?lines=%1").arg(lines))));
    watchReply(reply, 10000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        QJsonArray logLines;
        QString parseError;
        if (!parseRootArray(body, "Admin logs response", &logLines, &parseError)) {
            if (onError) onError(parseError);
            return;
        }
        QStringList lines;
        for (const auto &v : logLines)
            lines.append(v.toString());
        if (onSuccess) onSuccess(lines.join('\n'));
    });
}

void ApiService::fetchAdminAudit(const QString &orgId,
                                  const QString &action,
                                  int limit,
                                  std::function<void(std::vector<AuditLogDto>)> onSuccess,
                                  std::function<void(QString)> onError)
{
    QString path = QString("/api/v1/admin/audit?limit=%1").arg(limit);
    if (!orgId.isEmpty())
        path += "&org_id=" + QString::fromUtf8(QUrl::toPercentEncoding(orgId));
    if (!action.isEmpty())
        path += "&action=" + QString::fromUtf8(QUrl::toPercentEncoding(action));
    auto *reply = m_nam->get(makeAuthRequest(urlFor(path)));
    watchReply(reply, 10000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        QJsonArray auditItems;
        QString parseError;
        if (!parseRootArray(body, "Admin audit response", &auditItems, &parseError)) {
            if (onError) onError(parseError);
            return;
        }
        std::vector<AuditLogDto> result;
        for (const auto &v : auditItems) {
            const auto obj = v.toObject();
            AuditLogDto a;
            a.id = obj.value("id").toString();
            a.userId = obj.value("userId").toString();
            a.userEmail = obj.value("userEmail").toString();
            a.orgId = obj.value("orgId").toString();
            a.action = obj.value("action").toString();
            a.resourceType = obj.value("resourceType").toString();
            a.resourceId = obj.value("resourceId").toString();
            a.detail = obj.value("detail").toString();
            a.impersonatedBy = obj.value("impersonatedBy").toString();
            a.ip = obj.value("ip").toString();
            a.createdAt = obj.value("createdAt").toString();
            result.push_back(a);
        }
        if (onSuccess) onSuccess(result);
    });
}

void ApiService::impersonateUser(const QString &userId,
                                  std::function<void(ImpersonateDto)> onSuccess,
                                  std::function<void(QString)> onError)
{
    auto *reply =
        m_nam->post(makeAuthRequest(urlFor("/api/v1/admin/impersonate/" + userId)), QByteArray());
    watchReply(reply, 8000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        const auto obj = QJsonDocument::fromJson(body).object();
        if (onSuccess)
            onSuccess(ImpersonateDto{
                .accessToken = obj.value("accessToken").toString(),
                .userId = obj.value("userId").toString(),
                .userEmail = obj.value("userEmail").toString(),
                .userFullName = obj.value("userFullName").toString(),
                .orgId = obj.value("orgId").toString(),
                .role = obj.value("role").toString(),
                .expiresInMinutes = obj.value("expiresInMinutes").toInt(15),
            });
    });
}

void ApiService::fetchAdminCompanies(std::function<void(std::vector<CompanyDto>)> onSuccess,
                                      std::function<void(QString)> onError)
{
    auto *reply = m_nam->get(makeAuthRequest(urlFor("/api/v1/admin/companies")));
    watchReply(reply, 8000, [onSuccess, onError](QByteArray body, QString err) {
        if (!err.isEmpty()) { if (onError) onError(err); return; }
        QJsonArray items;
        QString parseError;
        if (!parseObjectArrayField(body, "Admin companies response", "items", &items, &parseError)) {
            if (onError) onError(parseError);
            return;
        }
        std::vector<CompanyDto> result;
        for (const auto &v : items) {
            const auto obj = v.toObject();
            CompanyDto c;
            c.id = obj.value("id").toString();
            c.name = obj.value("name").toString();
            c.ico = obj.value("ico").toString();
            c.email = obj.value("email").toString();
            c.phone = obj.value("phone").toString();
            c.userCount = obj.value("userCount").toInt();
            result.push_back(c);
        }
        if (onSuccess) onSuccess(result);
    });
}
