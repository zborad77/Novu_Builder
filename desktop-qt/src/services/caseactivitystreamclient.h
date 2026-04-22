#pragma once

#include <QElapsedTimer>
#include <QString>
#include <QUrl>

#include "icaseactivitystreamclient.h"

class QTimer;
class QWebSocket;
class SessionService;

class CaseActivityStreamClient : public ICaseActivityStreamClient
{
    Q_OBJECT
public:
    explicit CaseActivityStreamClient(SessionService &session, QObject *parent = nullptr);

    void refreshConnection();
    void subscribeToCase(const QString &caseId, const QString &jobId = QString()) override;
    void clearSubscription() override;
    void close();
    [[nodiscard]] bool isConnected() const override;

private:
    [[nodiscard]] QUrl buildDesiredUrl() const;
    [[nodiscard]] bool shouldMaintainConnection() const;
    void openSocket(const QUrl &url);
    void scheduleReconnect();
    void stopReconnect();
    void stopTransportTimers();
    void emitConnectionStateIfChanged();
    void sendCurrentSubscription();
    void handleTextMessage(const QString &message);
    void handleProtocolFailure(const QString &reason);

    SessionService &m_session;
    QWebSocket *m_socket = nullptr;
    QTimer *m_reconnectTimer = nullptr;
    QTimer *m_heartbeatTimer = nullptr;
    QTimer *m_staleTimer = nullptr;
    QUrl m_activeUrl;
    QString m_caseId;
    QString m_jobId;
    int m_reconnectAttempt = 0;
    bool m_reportedConnected = false;
    QElapsedTimer m_lastPongAt;
};
