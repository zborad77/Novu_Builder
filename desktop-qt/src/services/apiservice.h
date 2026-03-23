#pragma once

#include <QByteArray>
#include <QPointF>
#include <QString>
#include <QVector>
#include <vector>

#include "dto/adminjobdto.h"
#include "dto/adminuserdto.h"
#include "dto/casedto.h"
#include "dto/exportdto.h"
#include "dto/imagedto.h"
#include "dto/loginresultdto.h"
#include "dto/proposaldraftpatchdto.h"
#include "dto/uploadimagedto.h"

class QNetworkRequest;
class QUrl;

class ApiService
{
public:
    explicit ApiService(QString baseUrl = "http://127.0.0.1:8000/api/v1");

    static void setGlobalToken(const QString &bearerToken);
    static void clearGlobalToken();
    [[nodiscard]] static bool sessionExpired();
    static void clearSessionExpired();
    static void markSessionExpired();

    static void setGlobalBaseUrl(const QString &baseUrl);
    [[nodiscard]] static QString globalBaseUrl();

    [[nodiscard]] LoginResultDto login(
        const QString &email,
        const QString &password,
        QString *errorMessage = nullptr) const;

    [[nodiscard]] QString baseUrl() const;
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

private:
    [[nodiscard]] QNetworkRequest makeAuthRequest(const QUrl &url) const;

    QString m_baseUrl;
    static QString s_bearerToken;
    static bool s_sessionExpired;
    static QString s_globalBaseUrl;
};
