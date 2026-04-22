#include "casedetailviewmodel.h"

#include "services/apiservice.h"
#include "services/caseactivityservice.h"
#include "services/sessionservice.h"

namespace {
constexpr int kAnalysisMonitoringTickSeconds = 2;

bool hasPendingServerImageStatuses(const std::vector<ImageDto> &images)
{
    for (const auto &image : images) {
        if (image.processingStatus != "ready" && image.processingStatus != "failed") {
            return true;
        }
    }
    return false;
}

bool isTerminalAnalysisStatus(const QString &status)
{
    return status == "completed"
        || status == "failed"
        || status == "canceled"
        || status == "dead_letter";
}
}

CaseDetailViewModel::CaseDetailViewModel(SessionService &session, QObject *parent)
    : QObject(parent)
    , m_api(new ApiService(session, this))
    , m_caseActivity(new CaseActivityService(session, this))
{
    connect(m_api, &ApiService::sessionExpired, this, [this]() {
        emit sessionExpiredDetected();
    });
    connect(m_caseActivity, &CaseActivityService::sessionExpired, this, [this]() {
        emit sessionExpiredDetected();
    });
    connect(m_caseActivity, &CaseActivityService::imageStatusesReceived, this,
        [this](const QString &caseId, std::vector<ImageDto> images) {
            if (caseId != m_monitoredImageCaseId) {
                return;
            }
            const bool hasPending = hasPendingServerImageStatuses(images);
            emit imageMonitoringUpdated(std::move(images), hasPending);
            if (!hasPending && !m_monitoredImageCaseId.isEmpty()) {
                m_caseActivity->stopImageStatusMonitoring();
                loadCase(m_monitoredImageCaseId);
                m_monitoredImageCaseId.clear();
            }
        });
    connect(m_caseActivity, &CaseActivityService::imageMonitoringTimedOut, this, [this]() {
        m_monitoredImageCaseId.clear();
        emit imageMonitoringTimedOut();
    });
    connect(m_caseActivity, &CaseActivityService::imageMonitoringFailed, this, [this](const QString &message) {
        m_monitoredImageCaseId.clear();
        emit imageMonitoringFailed(message);
    });
    connect(m_caseActivity, &CaseActivityService::analysisStatusReceived, this,
        [this](const QString &caseId, const QString &jobId, const QString &status) {
            if (caseId != m_monitoredAnalysisCaseId || jobId != m_monitoredAnalysisJobId) {
                return;
            }
            m_analysisMonitoringElapsedSeconds += kAnalysisMonitoringTickSeconds;
            emit analysisMonitoringUpdated(status, m_analysisMonitoringElapsedSeconds);
            if (!isTerminalAnalysisStatus(status)) {
                return;
            }

            m_caseActivity->stopAnalysisStatusMonitoring();
            emit analysisMonitoringFinished(status);
            if (status == "completed" && !m_monitoredAnalysisCaseId.isEmpty()) {
                loadCase(m_monitoredAnalysisCaseId);
            }
            m_monitoredAnalysisCaseId.clear();
            m_monitoredAnalysisJobId.clear();
            m_analysisMonitoringElapsedSeconds = 0;
        });
    connect(m_caseActivity, &CaseActivityService::analysisMonitoringTimedOut, this, [this]() {
        m_monitoredAnalysisCaseId.clear();
        m_monitoredAnalysisJobId.clear();
        m_analysisMonitoringElapsedSeconds = 0;
        emit analysisMonitoringTimedOut();
    });
    connect(m_caseActivity, &CaseActivityService::analysisMonitoringFailed, this, [this](const QString &message) {
        m_monitoredAnalysisCaseId.clear();
        m_monitoredAnalysisJobId.clear();
        m_analysisMonitoringElapsedSeconds = 0;
        emit analysisMonitoringFailed(message);
    });
}

void CaseDetailViewModel::loadCase(const QString &caseId)
{
    emit loadingChanged(true);
    m_api->fetchCaseDetail(caseId,
        [this](CaseDto dto) {
            emit loadingChanged(false);
            emit caseLoaded(std::move(dto));
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::loadImages(const QString &caseId)
{
    emit loadingChanged(true);
    m_api->fetchCaseImages(caseId,
        [this](std::vector<ImageDto> images) {
            emit loadingChanged(false);
            emit imagesLoaded(std::move(images));
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::saveProposalDraft(const QString &caseId, const ProposalDraftPatchDto &draft)
{
    emit loadingChanged(true);
    m_api->updateCaseProposalDraft(
        caseId,
        draft,
        [this](CaseDto updatedCase) {
            emit loadingChanged(false);
            emit proposalDraftSaved(std::move(updatedCase));
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::triggerAnalysis(const QString &caseId)
{
    emit loadingChanged(true);
    m_api->triggerAnalysisJob(
        caseId,
        [this](QString jobId) {
            emit loadingChanged(false);
            emit analysisTriggered(std::move(jobId));
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::confirmSelectionArea(const QString &caseId,
                                               const QString &analysisResultId,
                                               const QVector<QPointF> &polygon,
                                               double manualAreaSqm)
{
    emit loadingChanged(true);
    m_api->patchAnalysisSelection(
        caseId,
        analysisResultId,
        polygon,
        manualAreaSqm,
        [this, caseId]() {
            m_api->fetchCaseDetail(
                caseId,
                [this](CaseDto updatedCase) {
                    emit loadingChanged(false);
                    emit analysisSelectionConfirmed(std::move(updatedCase));
                },
                [this](const QString &err) {
                    emit loadingChanged(false);
                    emit errorOccurred(err);
                });
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::startImageStatusMonitoring(const QString &caseId)
{
    m_monitoredImageCaseId = caseId;
    m_caseActivity->startImageStatusMonitoring(caseId);
}

void CaseDetailViewModel::stopImageStatusMonitoring()
{
    m_monitoredImageCaseId.clear();
    m_caseActivity->stopImageStatusMonitoring();
}

void CaseDetailViewModel::startAnalysisStatusMonitoring(const QString &caseId, const QString &jobId)
{
    m_monitoredAnalysisCaseId = caseId;
    m_monitoredAnalysisJobId = jobId;
    m_analysisMonitoringElapsedSeconds = 0;
    m_caseActivity->startAnalysisStatusMonitoring(caseId, jobId);
}

void CaseDetailViewModel::stopAnalysisStatusMonitoring()
{
    m_monitoredAnalysisCaseId.clear();
    m_monitoredAnalysisJobId.clear();
    m_analysisMonitoringElapsedSeconds = 0;
    m_caseActivity->stopAnalysisStatusMonitoring();
}

void CaseDetailViewModel::setPrimaryImage(const QString &caseId, const QString &imageId)
{
    emit loadingChanged(true);
    m_api->setCasePrimaryImage(caseId, imageId,
        [this, caseId]() {
            m_api->fetchCaseImages(
                caseId,
                [this](std::vector<ImageDto> images) {
                    emit loadingChanged(false);
                    emit primaryImageUpdated(std::move(images));
                },
                [this](const QString &err) {
                    emit loadingChanged(false);
                    emit errorOccurred(err);
                });
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}

void CaseDetailViewModel::setAnalysisReferenceImage(const QString &caseId, const QString &imageId)
{
    emit loadingChanged(true);
    m_api->setCaseAnalysisReferenceImage(caseId, imageId,
        [this, caseId]() {
            m_api->fetchCaseImages(
                caseId,
                [this](std::vector<ImageDto> images) {
                    emit loadingChanged(false);
                    emit analysisReferenceUpdated(std::move(images));
                },
                [this](const QString &err) {
                    emit loadingChanged(false);
                    emit errorOccurred(err);
                });
        },
        [this](const QString &err) {
            emit loadingChanged(false);
            emit errorOccurred(err);
        });
}
