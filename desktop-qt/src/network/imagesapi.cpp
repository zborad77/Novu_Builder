#include "imagesapi.h"

#include <QHttpMultiPart>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
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

} // namespace

std::vector<ImageDto> ImagesApi::fetchCaseImages(const QString &caseId, QString *errorMessage) const
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

std::vector<ImageDto> ImagesApi::moveCaseImage(
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

bool ImagesApi::setCasePrimaryImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
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

bool ImagesApi::setCaseAnalysisReferenceImage(const QString &caseId, const QString &imageId, QString *errorMessage) const
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

bool ImagesApi::uploadCaseImages(const QString &caseId, const std::vector<UploadImageDto> &images, QString *errorMessage) const
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
    const auto token = globalToken();
    if (!token.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
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

QByteArray ImagesApi::fetchImageData(const QString &imageUrl, QString *errorMessage) const
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
    const auto token = globalToken();
    if (!token.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
    }

    auto *reply = manager.get(request);

    const auto payload = waitForReply(reply, 5000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return payload;
}
