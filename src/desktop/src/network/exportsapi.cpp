#include "exportsapi.h"

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
} // namespace

ExportDto ExportsApi::triggerExport(const QString &caseId, const QString &exportType, QString *errorMessage) const
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

QByteArray ExportsApi::downloadExportFile(const QString &downloadUrl, QString *errorMessage) const
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
    const auto token = globalToken();
    if (!token.isEmpty()) {
        request.setRawHeader("Authorization", QByteArray("Bearer ") + token.toUtf8());
    }
    auto *reply = manager.get(request);

    const auto payload = waitForReply(reply, 15000, errorMessage);
    if (payload.isNull()) {
        return {};
    }
    return payload;
}
