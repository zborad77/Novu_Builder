#pragma once

#include <QObject>
#include <QString>
#include <functional>
#include <vector>

#include "dto/imagedto.h"
#include "icaseactivitystreamclient.h"

class ApiService;
class QTimer;
class SessionService;

class CaseActivityService : public QObject
{
    Q_OBJECT
public:
    explicit CaseActivityService(SessionService &session, QObject *parent = nullptr);
    explicit CaseActivityService(ICaseActivityStreamClient *streamClient, QObject *parent = nullptr);

    void startImageStatusMonitoring(const QString &caseId);
    void stopImageStatusMonitoring();

    void startAnalysisStatusMonitoring(const QString &caseId, const QString &jobId);
    void stopAnalysisStatusMonitoring();

signals:
    void imageStatusesReceived(QString caseId, std::vector<ImageDto> images);
    void imageMonitoringTimedOut();
    void imageMonitoringFailed(QString message);

    void analysisStatusReceived(QString caseId, QString jobId, QString status);
    void analysisMonitoringTimedOut();
    void analysisMonitoringFailed(QString message);

    void sessionExpired();

protected:
    virtual void apiGetAnalysisJobStatus(const QString &jobId,
                                         std::function<void(QString)> onSuccess,
                                         std::function<void(QString)> onError);
    virtual void apiFetchCaseImages(const QString &caseId,
                                     std::function<void(std::vector<ImageDto>)> onSuccess,
                                     std::function<void(QString)> onError);

private:
    void initConnections();
    void applyTransportState();
    void updateRealtimeSubscription();
    void startImagePollingFallback();
    void stopImagePollingFallback();
    void startAnalysisPollingFallback();
    void stopAnalysisPollingFallback();
    void refreshImagesFromRealtime();
    [[nodiscard]] bool canUseRealtimeTransport() const;
    [[nodiscard]] bool hasCrossCaseMonitoring() const;

    void pollImageStatuses();
    void pollAnalysisStatus();

    ApiService *m_api = nullptr;
    ICaseActivityStreamClient *m_streamClient = nullptr;
    QTimer *m_imagePollingTimer = nullptr;
    QTimer *m_analysisPollingTimer = nullptr;
    QTimer *m_imageRefreshDebounceTimer = nullptr;
    QString m_monitoredImageCaseId;
    QString m_monitoredAnalysisCaseId;
    QString m_monitoredAnalysisJobId;
    QString m_lastAnalysisJobStatus;
    int m_remainingImagePollAttempts = 0;
    int m_remainingAnalysisPollAttempts = 0;
    bool m_wasRealtimeAvailable = false;
    bool m_hasReceivedInitialSnapshot = false;
};
