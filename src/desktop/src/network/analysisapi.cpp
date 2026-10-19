#include "analysisapi.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QUrl>

QString AnalysisApi::triggerAnalysisJob(const QString &caseId, QString *errorMessage) const
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

QString AnalysisApi::getAnalysisJobStatus(const QString &jobId, QString *errorMessage) const
{
    if (errorMessage) errorMessage->clear();

    QNetworkAccessManager manager;
    const auto url = QUrl(QString("%1/analysis-jobs/%2").arg(m_baseUrl, jobId));
    auto *reply = manager.get(makeAuthRequest(url));

    const auto response = waitForReply(reply, 6000, errorMessage);
    if (response.isNull()) return {};

    return QJsonDocument::fromJson(response).object().value("status").toString();
}

bool AnalysisApi::patchAnalysisSelection(
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
