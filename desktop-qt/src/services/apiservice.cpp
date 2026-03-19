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
    proposalMaterials.reserve(materials.size());
    for (const auto &itemValue : materials) {
        const auto itemObject = itemValue.toObject();
        QString label = itemObject.value("name").toString();
        if (itemObject.value("quantity").isDouble() && !itemObject.value("unit").toString().isEmpty()) {
            label += QString(" | %1 %2")
                         .arg(itemObject.value("quantity").toDouble(), 0, 'f', 1)
                         .arg(itemObject.value("unit").toString());
        }
        if (itemObject.value("totalPrice").isDouble()) {
            label += QString(" | %1 CZK").arg(itemObject.value("totalPrice").toDouble(), 0, 'f', 2);
        }
        if (!label.isEmpty()) {
            proposalMaterials.push_back(label);
        }
    }

    return {
        .id = rootObject.value("id").toString(),
        .title = rootObject.value("title").toString(),
        .status = rootObject.value("status").toString(),
        .isReferenceDataset = rootObject.value("isReferenceDataset").toBool(),
        .addressLabel = location.value("addressLabel").toString(),
        .description = rootObject.value("description").toString(),
        .propertyType = rootObject.value("propertyType").toString(),
        .repairScope = rootObject.value("repairScope").toString(),
        .areaLabel = areaLabel,
        .proposalStatus = proposalDraft.value("status").toString(),
        .proposalSubject = proposalDraft.value("subject").toString(),
        .proposalSummary = proposalDraft.value("summary").toString(),
        .proposalMaterialCostLabel = formatCurrencyLabel(proposalDraft.value("materialCost")),
        .proposalLaborCostLabel = formatCurrencyLabel(proposalDraft.value("laborCost")),
        .proposalAmortizationLabel = formatCurrencyLabel(proposalDraft.value("amortization")),
        .proposalMarginLabel = formatCurrencyLabel(proposalDraft.value("margin")),
        .proposalTotalPriceLabel = formatCurrencyLabel(proposalDraft.value("totalPrice")),
        .proposalRecommendedSupplier = proposalDraft.value("recommendedSupplier").toString(),
        .proposalRecommendedCompany = proposalDraft.value("recommendedCompany").toString(),
        .proposalWorkItems = proposalWorkItems,
        .proposalMaterials = proposalMaterials,
        .expectedScope = referenceExpectations.value("expectedScope").toString(),
        .expectedPrimaryFilename = referenceExpectations.value("expectedPrimaryFilename").toString(),
        .expectedAnalysisReferenceFilename = referenceExpectations.value("expectedAnalysisReferenceFilename").toString(),
        .referenceSourcePage = referenceExpectations.value("sourcePage").toString(),
        .finalProposalStatus = finalProposal.value("status").toString(),
        .finalProposalDraftVersionLabel = finalProposal.value("draftVersion").isDouble()
            ? QString("Draft verze %1").arg(finalProposal.value("draftVersion").toInt())
            : QString(),
        .finalProposalSubject = finalProposal.value("subject").toString(),
        .finalProposalSummary = finalProposal.value("summary").toString(),
        .finalProposalTotalPriceLabel = formatCurrencyLabel(finalProposal.value("totalPrice"))
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
}

ApiService::ApiService(QString baseUrl)
    : m_baseUrl(std::move(baseUrl))
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
    QNetworkRequest request(QUrl(m_baseUrl + "/cases"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    std::vector<CaseDto> result;

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nacist cases: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return result;
    }

    const auto payload = reply->readAll();
    reply->deleteLater();

    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved pro seznam cases.";
        }
        return result;
    }

    const auto rootObject = document.object();
    const auto items = rootObject.value("items").toArray();

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

QString ApiService::duplicateCase(const QString &caseId, const QString &mode, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/duplicate"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    const auto payload = QJsonDocument(QJsonObject{{"mode", mode}}).toJson(QJsonDocument::Compact);
    auto *reply = manager.post(request, payload);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se vytvorit kopii zakazky: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return {};
    }

    const auto responsePayload = reply->readAll();
    reply->deleteLater();

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
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/send"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.post(request, QByteArray());

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se odeslat zakazku: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return false;
    }

    reply->deleteLater();
    return true;
}

CaseDto ApiService::fetchCaseDetail(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nacist detail case: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return {};
    }

    const auto payload = reply->readAll();
    reply->deleteLater();

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
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/proposal-draft"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    const auto payload = QJsonDocument(QJsonObject{
        {"subject", proposalDraft.subject},
        {"summary", proposalDraft.summary},
        {"materialCost", proposalDraft.materialCost},
        {"laborCost", proposalDraft.laborCost},
        {"amortization", proposalDraft.amortization},
        {"margin", proposalDraft.margin},
        {"recommendedSupplier", proposalDraft.recommendedSupplier},
        {"recommendedCompany", proposalDraft.recommendedCompany},
    }).toJson(QJsonDocument::Compact);
    auto *reply = manager.sendCustomRequest(request, "PATCH", payload);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se ulozit navrh nabidky: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return {};
    }

    const auto responsePayload = reply->readAll();
    reply->deleteLater();
    return parseCaseDetailResponse(responsePayload, errorMessage);
}

CaseDto ApiService::createCaseFinalProposal(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/final-proposal"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.post(request, QByteArray());

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se vytvorit vyslednou nabidku: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return {};
    }

    const auto responsePayload = reply->readAll();
    reply->deleteLater();
    return parseCaseDetailResponse(responsePayload, errorMessage);
}

std::vector<ImageDto> ApiService::fetchCaseImages(const QString &caseId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/images"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    std::vector<ImageDto> result;

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nacist images: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return result;
    }

    const auto payload = reply->readAll();
    reply->deleteLater();

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
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/move"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    const auto payload = QJsonDocument(QJsonObject{{"direction", direction}}).toJson(QJsonDocument::Compact);
    auto *reply = manager.sendCustomRequest(request, "PATCH", payload);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    std::vector<ImageDto> result;

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se zmenit poradi fotek: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return result;
    }

    const auto responsePayload = reply->readAll();
    reply->deleteLater();
    return parseImageListResponse(responsePayload, errorMessage);
}

bool ApiService::setCasePrimaryImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/primary"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.sendCustomRequest(request, "PATCH");

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nastavit hlavni fotku: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return false;
    }

    reply->deleteLater();
    return true;
}

bool ApiService::setCaseAnalysisReferenceImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
{
    if (errorMessage) {
        errorMessage->clear();
    }

    QNetworkAccessManager manager;
    QNetworkRequest request(QUrl(m_baseUrl + "/cases/" + caseId + "/images/" + imageId + "/analysis-reference"));
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");

    auto *reply = manager.sendCustomRequest(request, "PATCH");

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nastavit referencni fotku pro analyzu: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return false;
    }

    reply->deleteLater();
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

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(15000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se odeslat fotky na server: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return false;
    }

    const auto payload = reply->readAll();
    reply->deleteLater();

    const auto document = QJsonDocument::fromJson(payload);
    if (!document.isObject()) {
        if (errorMessage) {
            *errorMessage = "Backend vratil neplatnou odpoved po uploadu fotek.";
        }
        return false;
    }

    return true;
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

    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timeoutTimer;
    timeoutTimer.setSingleShot(true);

    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timeoutTimer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) {
            reply->abort();
        }
    });

    timeoutTimer.start(5000);
    loop.exec();

    if (reply->error() != QNetworkReply::NoError) {
        if (errorMessage) {
            *errorMessage = QString("Nepodarilo se nacist preview: %1").arg(reply->errorString());
        }
        reply->deleteLater();
        return {};
    }

    const auto payload = reply->readAll();
    reply->deleteLater();
    return payload;
}
