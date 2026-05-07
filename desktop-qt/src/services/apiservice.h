#pragma once

#include <QByteArray>
#include <QPointF>
#include <QString>
#include <QVector>
#include <vector>

#include "network/apiclient.h"
#include "models/adminjobdto.h"
#include "models/adminuserdto.h"
#include "models/auditlogdto.h"
#include "models/companydto.h"
#include "models/impersonatedto.h"
#include "models/casedto.h"
#include "models/exportdto.h"
#include "models/imagedto.h"
#include "models/proposaldraftpatchdto.h"
#include "models/uploadimagedto.h"

class ApiService : public ApiClient
{
public:
    using ApiClient::ApiClient;
    [[nodiscard]] std::vector<CaseDto> fetchCases(QString *errorMessage = nullptr) const;
    [[nodiscard]] QString createCase(
        const QString &title,
        const QString &addressLabel,
        const QString &repairScope,
        const QString &description,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QString duplicateCase(
        const QString &caseId,
        const QString &mode,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool sendCase(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto fetchCaseDetail(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto updateCaseProposalDraft(
        const QString &caseId,
        const ProposalDraftPatchDto &proposalDraft,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] CaseDto createCaseFinalProposal(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<ImageDto> fetchCaseImages(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] std::vector<ImageDto> moveCaseImage(
        const QString &caseId,
        const QString &imageId,
        const QString &direction,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCasePrimaryImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool setCaseAnalysisReferenceImage(
        const QString &caseId,
        const QString &imageId,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] bool uploadCaseImages(
        const QString &caseId,
        const std::vector<UploadImageDto> &images,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QByteArray fetchImageData(const QString &imageUrl, QString *errorMessage = nullptr) const;
    [[nodiscard]] QString triggerAnalysisJob(const QString &caseId, QString *errorMessage = nullptr) const;
    [[nodiscard]] QString getAnalysisJobStatus(const QString &jobId, QString *errorMessage = nullptr) const;
    [[nodiscard]] bool patchAnalysisSelection(
        const QString &caseId,
        const QString &analysisResultId,
        const QVector<QPointF> &polygon,
        double manualAreaSqm,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] ExportDto triggerExport(
        const QString &caseId,
        const QString &exportType,
        QString *errorMessage = nullptr) const;
    [[nodiscard]] QByteArray downloadExportFile(
        const QString &downloadUrl,
        QString *errorMessage = nullptr) const;

    // ── Admin (superadmin only) ────────────────────────────────────────────
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
