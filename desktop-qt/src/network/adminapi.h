#pragma once

#include "apiclient.h"
#include "models/adminjobdto.h"
#include "models/adminuserdto.h"
#include "models/auditlogdto.h"
#include "models/companydto.h"
#include "models/impersonatedto.h"

#include <QString>
#include <vector>

class AdminApi : public ApiClient
{
public:
    using ApiClient::ApiClient;

    [[nodiscard]] std::vector<AdminUserDto> fetchAdminUsers(
        const QString &orgId = {},
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool resetUserPassword(
        const QString &userId,
        const QString &newPassword,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<AdminJobDto> fetchAdminJobs(
        const QString &statusFilter = {},
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QString fetchAdminLogs(
        int lines = 200,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<AuditLogDto> fetchAdminAudit(
        const QString &orgId = {},
        const QString &action = {},
        int limit = 200,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] ImpersonateDto impersonateUser(
        const QString &userId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<CompanyDto> fetchAdminCompanies(
        QString *errorMessage = nullptr) const;
};
