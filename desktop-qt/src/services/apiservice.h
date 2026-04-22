#pragma once

#include <QByteArray>
#include <QObject>
#include <QPointF>
#include <QString>
#include <QVector>
#include <functional>
#include <vector>

#include "dto/adminjobdto.h"
#include "dto/adminuserdto.h"
#include "dto/auditlogdto.h"
#include "dto/companydto.h"
#include "dto/impersonatedto.h"
#include "dto/casedto.h"
#include "dto/exportdto.h"
#include "dto/imagedto.h"
#include "dto/loginresultdto.h"
#include "dto/proposaldraftpatchdto.h"
#include "dto/uploadimagedto.h"

class QNetworkAccessManager;
class QNetworkReply;
class QNetworkRequest;
class QUrl;
class SessionService;

class ApiService : public QObject
{
    Q_OBJECT
public:
    explicit ApiService(SessionService &session, QObject *parent = nullptr);

    // -- Global app config --
    static void setGlobalBaseUrl(const QString &url);
    [[nodiscard]] static QString globalBaseUrl();

    // -- Auth --
    void login(const QString &email,
               const QString &password,
               std::function<void(LoginResultDto)> onSuccess,
               std::function<void(QString)> onError = nullptr);

    // -- Cases --
    void fetchCases(std::function<void(std::vector<CaseDto>)> onSuccess,
                    std::function<void(QString)> onError = nullptr);

    void fetchCaseDetail(const QString &caseId,
                         std::function<void(CaseDto)> onSuccess,
                         std::function<void(QString)> onError = nullptr);

    void createCase(const QString &title,
                    const QString &addressLabel,
                    const QString &repairScope,
                    const QString &description,
                    std::function<void(QString /*newCaseId*/)> onSuccess,
                    std::function<void(QString)> onError = nullptr);

    void duplicateCase(const QString &caseId,
                       const QString &mode,
                       std::function<void(QString /*newCaseId*/)> onSuccess,
                       std::function<void(QString)> onError = nullptr);

    void sendCase(const QString &caseId,
                  std::function<void()> onSuccess,
                  std::function<void(QString)> onError = nullptr);

    void updateCaseProposalDraft(const QString &caseId,
                                  const ProposalDraftPatchDto &draft,
                                  std::function<void(CaseDto)> onSuccess,
                                  std::function<void(QString)> onError = nullptr);

    void createCaseFinalProposal(const QString &caseId,
                                  std::function<void(CaseDto)> onSuccess,
                                  std::function<void(QString)> onError = nullptr);

    // -- Images --
    void fetchCaseImages(const QString &caseId,
                         std::function<void(std::vector<ImageDto>)> onSuccess,
                         std::function<void(QString)> onError = nullptr);

    void moveCaseImage(const QString &caseId,
                       const QString &imageId,
                       const QString &direction,
                       std::function<void(std::vector<ImageDto>)> onSuccess,
                       std::function<void(QString)> onError = nullptr);

    void setCasePrimaryImage(const QString &caseId,
                              const QString &imageId,
                              std::function<void()> onSuccess,
                              std::function<void(QString)> onError = nullptr);

    void setCaseAnalysisReferenceImage(const QString &caseId,
                                        const QString &imageId,
                                        std::function<void()> onSuccess,
                                        std::function<void(QString)> onError = nullptr);

    void uploadCaseImages(const QString &caseId,
                          const std::vector<UploadImageDto> &images,
                          std::function<void()> onSuccess,
                          std::function<void(QString)> onError = nullptr);

    void fetchImageData(const QString &imageUrl,
                        std::function<void(QByteArray)> onSuccess,
                        std::function<void(QString)> onError = nullptr);

    // -- Analysis --
    void triggerAnalysisJob(const QString &caseId,
                            std::function<void(QString /*jobId*/)> onSuccess,
                            std::function<void(QString)> onError = nullptr);

    void getAnalysisJobStatus(const QString &jobId,
                              std::function<void(QString /*status*/)> onSuccess,
                              std::function<void(QString)> onError = nullptr);

    void patchAnalysisSelection(const QString &caseId,
                                 const QString &analysisResultId,
                                 const QVector<QPointF> &polygon,
                                 double manualAreaSqm,
                                 std::function<void()> onSuccess,
                                 std::function<void(QString)> onError = nullptr);

    // -- Exports --
    void triggerExport(const QString &caseId,
                       const QString &exportType,
                       std::function<void(ExportDto)> onSuccess,
                       std::function<void(QString)> onError = nullptr);

    void downloadExportFile(const QString &downloadUrl,
                            std::function<void(QByteArray)> onSuccess,
                            std::function<void(QString)> onError = nullptr);

    // -- Admin --
    void fetchAdminUsers(const QString &orgId,
                         std::function<void(std::vector<AdminUserDto>)> onSuccess,
                         std::function<void(QString)> onError = nullptr);

    void resetUserPassword(const QString &userId,
                           const QString &newPassword,
                           std::function<void()> onSuccess,
                           std::function<void(QString)> onError = nullptr);

    void fetchAdminJobs(const QString &statusFilter,
                        std::function<void(std::vector<AdminJobDto>)> onSuccess,
                        std::function<void(QString)> onError = nullptr);

    void fetchAdminLogs(int lines,
                        std::function<void(QString)> onSuccess,
                        std::function<void(QString)> onError = nullptr);

    void fetchAdminAudit(const QString &orgId,
                         const QString &action,
                         int limit,
                         std::function<void(std::vector<AuditLogDto>)> onSuccess,
                         std::function<void(QString)> onError = nullptr);

    void impersonateUser(const QString &userId,
                         std::function<void(ImpersonateDto)> onSuccess,
                         std::function<void(QString)> onError = nullptr);

    void fetchAdminCompanies(std::function<void(std::vector<CompanyDto>)> onSuccess,
                              std::function<void(QString)> onError = nullptr);

signals:
    void sessionExpired();

private:
    // Attach timeout + finished handler to reply.
    // callback(body, error): error is empty on success.
    // When notifySessionExpiry=true (default), 401 emits sessionExpired() signal.
    void watchReply(QNetworkReply *reply,
                    int timeoutMs,
                    std::function<void(QByteArray, QString)> callback,
                    bool notifySessionExpiry = true);

    [[nodiscard]] QNetworkRequest makeAuthRequest(const QUrl &url) const;
    [[nodiscard]] QUrl urlFor(const QString &path) const;
    [[nodiscard]] QUrl resolveAbsolute(const QString &urlOrPath) const;
    [[nodiscard]] QString bearerToken() const;

    QNetworkAccessManager *m_nam;
    SessionService *m_session;
    static QString s_globalBaseUrl;
};
