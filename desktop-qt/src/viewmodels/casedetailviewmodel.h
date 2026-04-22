#pragma once

#include <QObject>
#include <QPointF>
#include <QString>
#include <QVector>
#include <vector>

#include "dto/casedto.h"
#include "dto/imagedto.h"
#include "dto/proposaldraftpatchdto.h"

class ApiService;
class CaseActivityService;
class SessionService;

class CaseDetailViewModel : public QObject
{
    Q_OBJECT
public:
    explicit CaseDetailViewModel(SessionService &session, QObject *parent = nullptr);

    void loadCase(const QString &caseId);
    void loadImages(const QString &caseId);
    void saveProposalDraft(const QString &caseId, const ProposalDraftPatchDto &draft);
    void triggerAnalysis(const QString &caseId);
    void confirmSelectionArea(const QString &caseId,
                              const QString &analysisResultId,
                              const QVector<QPointF> &polygon,
                              double manualAreaSqm);
    void startImageStatusMonitoring(const QString &caseId);
    void stopImageStatusMonitoring();
    void startAnalysisStatusMonitoring(const QString &caseId, const QString &jobId);
    void stopAnalysisStatusMonitoring();
    void setPrimaryImage(const QString &caseId, const QString &imageId);
    void setAnalysisReferenceImage(const QString &caseId, const QString &imageId);

signals:
    void loadingChanged(bool loading);
    void caseLoaded(CaseDto caseData);
    void imagesLoaded(std::vector<ImageDto> images);
    void proposalDraftSaved(CaseDto caseData);
    void analysisTriggered(QString jobId);
    void analysisSelectionConfirmed(CaseDto caseData);
    void imageMonitoringUpdated(std::vector<ImageDto> images, bool hasPending);
    void imageMonitoringTimedOut();
    void imageMonitoringFailed(QString message);
    void analysisMonitoringUpdated(QString status, int elapsedSeconds);
    void analysisMonitoringFinished(QString status);
    void analysisMonitoringTimedOut();
    void analysisMonitoringFailed(QString message);
    void primaryImageUpdated(std::vector<ImageDto> images);
    void analysisReferenceUpdated(std::vector<ImageDto> images);
    void errorOccurred(QString message);
    void sessionExpiredDetected();

private:
    ApiService *m_api = nullptr;
    CaseActivityService *m_caseActivity = nullptr;
    QString m_monitoredImageCaseId;
    QString m_monitoredAnalysisCaseId;
    QString m_monitoredAnalysisJobId;
    int m_analysisMonitoringElapsedSeconds = 0;
};
