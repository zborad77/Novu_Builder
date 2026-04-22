#include "caseactivityservice.h"

#include <QTimer>

#include "apiservice.h"
#include "caseactivitystreamclient.h"
#include "sessionservice.h"

namespace {
constexpr int kImagePollingIntervalMs = 1500;
constexpr int kImagePollingAttemptLimit = 8;
constexpr int kAnalysisPollingIntervalMs = 2000;
constexpr int kAnalysisPollingAttemptLimit = 90;
constexpr int kRealtimeImageRefreshDebounceMs = 150;

bool isTerminalJobStatus(const QString &status)
{
    return status == QLatin1String("completed")
        || status == QLatin1String("failed")
        || status == QLatin1String("error")
        || status == QLatin1String("cancelled");
}
}

CaseActivityService::CaseActivityService(SessionService &session, QObject *parent)
    : QObject(parent)
    , m_api(new ApiService(session, this))
    , m_streamClient(session.caseActivityStreamClient())
    , m_imagePollingTimer(new QTimer(this))
    , m_analysisPollingTimer(new QTimer(this))
    , m_imageRefreshDebounceTimer(new QTimer(this))
{
    connect(m_api, &ApiService::sessionExpired, this, &CaseActivityService::sessionExpired);
    initConnections();
}

CaseActivityService::CaseActivityService(ICaseActivityStreamClient *streamClient, QObject *parent)
    : QObject(parent)
    , m_streamClient(streamClient)
    , m_imagePollingTimer(new QTimer(this))
    , m_analysisPollingTimer(new QTimer(this))
    , m_imageRefreshDebounceTimer(new QTimer(this))
{
    initConnections();
}

void CaseActivityService::initConnections()
{
    m_imagePollingTimer->setInterval(kImagePollingIntervalMs);
    connect(m_imagePollingTimer, &QTimer::timeout, this, &CaseActivityService::pollImageStatuses);

    m_analysisPollingTimer->setInterval(kAnalysisPollingIntervalMs);
    connect(m_analysisPollingTimer, &QTimer::timeout, this, &CaseActivityService::pollAnalysisStatus);

    m_imageRefreshDebounceTimer->setSingleShot(true);
    m_imageRefreshDebounceTimer->setInterval(kRealtimeImageRefreshDebounceMs);
    connect(m_imageRefreshDebounceTimer, &QTimer::timeout, this, &CaseActivityService::refreshImagesFromRealtime);

    if (!m_streamClient) {
        return;
    }

    connect(m_streamClient, &ICaseActivityStreamClient::sessionExpired,
            this, &CaseActivityService::sessionExpired);
    connect(m_streamClient, &ICaseActivityStreamClient::connectionStateChanged, this,
            [this](bool) {
                applyTransportState();
            });
    connect(m_streamClient, &ICaseActivityStreamClient::jobStatusChanged, this,
            [this](const QString &caseId, const QString &jobId, const QString &status) {
                if (caseId != m_monitoredAnalysisCaseId || jobId != m_monitoredAnalysisJobId) {
                    return;
                }
                if (status == m_lastAnalysisJobStatus) {
                    return;
                }
                if (isTerminalJobStatus(m_lastAnalysisJobStatus)) {
                    return;
                }
                m_lastAnalysisJobStatus = status;
                m_hasReceivedInitialSnapshot = true;
                emit analysisStatusReceived(caseId, jobId, status);
            });
    connect(m_streamClient, &ICaseActivityStreamClient::imageStatusChanged, this,
            [this](const QString &caseId, const QString &, const QString &, const QString &) {
                if (caseId != m_monitoredImageCaseId || !canUseRealtimeTransport()) {
                    return;
                }
                m_imageRefreshDebounceTimer->start();
            });
}

void CaseActivityService::apiGetAnalysisJobStatus(
    const QString &jobId,
    std::function<void(QString)> onSuccess,
    std::function<void(QString)> onError)
{
    m_api->getAnalysisJobStatus(jobId, std::move(onSuccess), std::move(onError));
}

void CaseActivityService::apiFetchCaseImages(
    const QString &caseId,
    std::function<void(std::vector<ImageDto>)> onSuccess,
    std::function<void(QString)> onError)
{
    m_api->fetchCaseImages(caseId, std::move(onSuccess), std::move(onError));
}

void CaseActivityService::startImageStatusMonitoring(const QString &caseId)
{
    if (caseId.isEmpty()) {
        stopImageStatusMonitoring();
        return;
    }

    m_monitoredImageCaseId = caseId;
    m_remainingImagePollAttempts = kImagePollingAttemptLimit;
    applyTransportState();
}

void CaseActivityService::stopImageStatusMonitoring()
{
    stopImagePollingFallback();
    m_monitoredImageCaseId.clear();
    m_remainingImagePollAttempts = 0;
    updateRealtimeSubscription();
}

void CaseActivityService::startAnalysisStatusMonitoring(const QString &caseId, const QString &jobId)
{
    if (caseId.isEmpty() || jobId.isEmpty()) {
        stopAnalysisStatusMonitoring();
        return;
    }

    if (jobId != m_monitoredAnalysisJobId) {
        m_lastAnalysisJobStatus.clear();
        m_hasReceivedInitialSnapshot = false;
    }
    m_monitoredAnalysisCaseId = caseId;
    m_monitoredAnalysisJobId = jobId;
    m_remainingAnalysisPollAttempts = kAnalysisPollingAttemptLimit;
    applyTransportState();
}

void CaseActivityService::stopAnalysisStatusMonitoring()
{
    stopAnalysisPollingFallback();
    m_monitoredAnalysisCaseId.clear();
    m_monitoredAnalysisJobId.clear();
    m_lastAnalysisJobStatus.clear();
    m_hasReceivedInitialSnapshot = false;
    m_remainingAnalysisPollAttempts = 0;
    updateRealtimeSubscription();
}

void CaseActivityService::applyTransportState()
{
    updateRealtimeSubscription();

    const bool realtimeAvailable = canUseRealtimeTransport();
    const bool justBecameAvailable = realtimeAvailable && !m_wasRealtimeAvailable;
    const bool justBecameUnavailable = !realtimeAvailable && m_wasRealtimeAvailable;
    m_wasRealtimeAvailable = realtimeAvailable;

    if (justBecameUnavailable) {
        m_hasReceivedInitialSnapshot = false;
    }

    if (realtimeAvailable) {
        stopImagePollingFallback();
        stopAnalysisPollingFallback();
        if (justBecameAvailable) {
            if (!m_monitoredImageCaseId.isEmpty()) {
                m_imageRefreshDebounceTimer->start();
            }
            if (!m_monitoredAnalysisCaseId.isEmpty() && !m_monitoredAnalysisJobId.isEmpty()
                && !isTerminalJobStatus(m_lastAnalysisJobStatus)
                && !m_hasReceivedInitialSnapshot) {
                pollAnalysisStatus();
            }
        }
        return;
    }

    if (!m_monitoredImageCaseId.isEmpty()) {
        startImagePollingFallback();
    } else {
        stopImagePollingFallback();
    }

    if (!m_monitoredAnalysisCaseId.isEmpty() && !m_monitoredAnalysisJobId.isEmpty()) {
        startAnalysisPollingFallback();
    } else {
        stopAnalysisPollingFallback();
    }
}

void CaseActivityService::updateRealtimeSubscription()
{
    if (!m_streamClient) {
        return;
    }

    if (hasCrossCaseMonitoring()) {
        m_streamClient->clearSubscription();
        return;
    }

    const QString caseId = !m_monitoredAnalysisCaseId.isEmpty()
        ? m_monitoredAnalysisCaseId
        : m_monitoredImageCaseId;
    if (caseId.isEmpty()) {
        m_streamClient->clearSubscription();
        return;
    }

    m_streamClient->subscribeToCase(caseId, m_monitoredAnalysisJobId);
}

void CaseActivityService::startImagePollingFallback()
{
    if (m_imagePollingTimer->isActive()) {
        return;
    }
    pollImageStatuses();
    if (!m_monitoredImageCaseId.isEmpty()) {
        m_imagePollingTimer->start();
    }
}

void CaseActivityService::stopImagePollingFallback()
{
    if (m_imagePollingTimer->isActive()) {
        m_imagePollingTimer->stop();
    }
    if (m_imageRefreshDebounceTimer->isActive()) {
        m_imageRefreshDebounceTimer->stop();
    }
}

void CaseActivityService::startAnalysisPollingFallback()
{
    if (m_analysisPollingTimer->isActive()) {
        return;
    }
    pollAnalysisStatus();
    if (!m_monitoredAnalysisCaseId.isEmpty() && !m_monitoredAnalysisJobId.isEmpty()) {
        m_analysisPollingTimer->start();
    }
}

void CaseActivityService::stopAnalysisPollingFallback()
{
    if (m_analysisPollingTimer->isActive()) {
        m_analysisPollingTimer->stop();
    }
}

void CaseActivityService::refreshImagesFromRealtime()
{
    if (m_monitoredImageCaseId.isEmpty() || !canUseRealtimeTransport()) {
        return;
    }

    const QString caseId = m_monitoredImageCaseId;
    apiFetchCaseImages(
        caseId,
        [this, caseId](std::vector<ImageDto> images) {
            if (caseId != m_monitoredImageCaseId) {
                return;
            }
            emit imageStatusesReceived(caseId, std::move(images));
        },
        [this, caseId](const QString &) {
            if (caseId != m_monitoredImageCaseId) {
                return;
            }
            startImagePollingFallback();
        });
}

bool CaseActivityService::canUseRealtimeTransport() const
{
    return m_streamClient
        && m_streamClient->isConnected()
        && !hasCrossCaseMonitoring();
}

bool CaseActivityService::hasCrossCaseMonitoring() const
{
    return !m_monitoredImageCaseId.isEmpty()
        && !m_monitoredAnalysisCaseId.isEmpty()
        && m_monitoredImageCaseId != m_monitoredAnalysisCaseId;
}

void CaseActivityService::pollImageStatuses()
{
    if (m_monitoredImageCaseId.isEmpty()) {
        stopImagePollingFallback();
        return;
    }

    if (m_remainingImagePollAttempts <= 0) {
        stopImageStatusMonitoring();
        emit imageMonitoringTimedOut();
        return;
    }

    --m_remainingImagePollAttempts;
    const QString caseId = m_monitoredImageCaseId;

    apiFetchCaseImages(
        caseId,
        [this, caseId](std::vector<ImageDto> images) {
            if (caseId != m_monitoredImageCaseId) {
                return;
            }
            emit imageStatusesReceived(caseId, std::move(images));
        },
        [this, caseId](const QString &errorMessage) {
            if (caseId != m_monitoredImageCaseId) {
                return;
            }
            stopImageStatusMonitoring();
            emit imageMonitoringFailed(errorMessage);
        });
}

void CaseActivityService::pollAnalysisStatus()
{
    if (m_monitoredAnalysisCaseId.isEmpty() || m_monitoredAnalysisJobId.isEmpty()) {
        stopAnalysisPollingFallback();
        return;
    }

    if (m_remainingAnalysisPollAttempts <= 0) {
        stopAnalysisStatusMonitoring();
        emit analysisMonitoringTimedOut();
        return;
    }

    --m_remainingAnalysisPollAttempts;
    const QString caseId = m_monitoredAnalysisCaseId;
    const QString jobId = m_monitoredAnalysisJobId;

    apiGetAnalysisJobStatus(
        jobId,
        [this, caseId, jobId](QString status) {
            if (caseId != m_monitoredAnalysisCaseId || jobId != m_monitoredAnalysisJobId) {
                return;
            }
            if (status == m_lastAnalysisJobStatus) {
                return;
            }
            if (isTerminalJobStatus(m_lastAnalysisJobStatus)) {
                return;
            }
            m_lastAnalysisJobStatus = status;
            m_hasReceivedInitialSnapshot = true;
            emit analysisStatusReceived(caseId, jobId, std::move(status));
        },
        [this, caseId, jobId](const QString &errorMessage) {
            if (caseId != m_monitoredAnalysisCaseId || jobId != m_monitoredAnalysisJobId) {
                return;
            }
            stopAnalysisStatusMonitoring();
            emit analysisMonitoringFailed(errorMessage);
        });
}
