#include "adminapi.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QStringList>
#include <QUrl>

std::vector<AdminUserDto> AdminApi::fetchAdminUsers(const QString &orgId, QString *errorMessage) const
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

bool AdminApi::resetUserPassword(const QString &userId, const QString &newPassword, QString *errorMessage) const
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

std::vector<AdminJobDto> AdminApi::fetchAdminJobs(const QString &statusFilter, QString *errorMessage) const
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

QString AdminApi::fetchAdminLogs(int lines, QString *errorMessage) const
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

std::vector<AuditLogDto> AdminApi::fetchAdminAudit(const QString &orgId, const QString &action, int limit, QString *errorMessage) const
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

ImpersonateDto AdminApi::impersonateUser(const QString &userId, QString *errorMessage) const
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

std::vector<CompanyDto> AdminApi::fetchAdminCompanies(QString *errorMessage) const
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
