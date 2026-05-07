#include "apiservice.h"

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
    if (sessionExpired()) return false;

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

std::vector<AuditLogDto> ApiService::fetchAdminAudit(const QString &orgId, const QString &action, int limit, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QString path = QString("/api/v1/admin/audit?limit=%1").arg(limit);
    if (!orgId.isEmpty())
        path += "&org_id=" + QString::fromUtf8(QUrl::toPercentEncoding(orgId));
    if (!action.isEmpty())
        path += "&action=" + QString::fromUtf8(QUrl::toPercentEncoding(action));

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + path)));
    const auto payload = waitForReply(reply, 10000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isArray()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    std::vector<AuditLogDto> result;
    for (const auto &item : doc.array()) {
        const auto obj = item.toObject();
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
    return result;
}

ImpersonateDto ApiService::impersonateUser(const QString &userId, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QNetworkAccessManager manager;
    const QUrl url(m_baseUrl + "/api/v1/admin/impersonate/" + userId);
    QNetworkRequest req = makeAuthRequest(url);
    auto *reply = manager.post(req, QByteArray());
    const auto payload = waitForReply(reply, 8000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    const auto obj = doc.object();
    if (obj.contains("detail")) {
        if (errorMessage) *errorMessage = obj.value("detail").toString();
        return {};
    }

    return ImpersonateDto{
        .accessToken = obj.value("accessToken").toString(),
        .userId = obj.value("userId").toString(),
        .userEmail = obj.value("userEmail").toString(),
        .userFullName = obj.value("userFullName").toString(),
        .orgId = obj.value("orgId").toString(),
        .role = obj.value("role").toString(),
        .expiresInMinutes = obj.value("expiresInMinutes").toInt(15),
    };
}

std::vector<CompanyDto> ApiService::fetchAdminCompanies(QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QNetworkAccessManager manager;
    auto *reply = manager.get(makeAuthRequest(QUrl(m_baseUrl + "/api/v1/admin/companies")));
    const auto payload = waitForReply(reply, 8000, errorMessage);
    if (payload.isNull()) return {};

    const auto doc = QJsonDocument::fromJson(payload);
    if (!doc.isObject()) {
        if (errorMessage) *errorMessage = "Neplatna odpoved serveru.";
        return {};
    }

    std::vector<CompanyDto> result;
    for (const auto &item : doc.object().value("items").toArray()) {
        const auto obj = item.toObject();
        CompanyDto c;
        c.id = obj.value("id").toString();
        c.name = obj.value("name").toString();
        c.ico = obj.value("ico").toString();
        c.email = obj.value("email").toString();
        c.phone = obj.value("phone").toString();
        c.userCount = obj.value("userCount").toInt();
        result.push_back(c);
    }
    return result;
}
