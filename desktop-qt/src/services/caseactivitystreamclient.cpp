#include "caseactivitystreamclient.h"

#include <QAbstractSocket>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QTimer>
#include <QUrlQuery>
#include <QWebSocket>

#include "apiservice.h"
#include "sessionservice.h"

namespace {
constexpr int kReconnectInitialDelayMs = 1000;
constexpr int kReconnectMaxDelayMs = 15000;
constexpr int kHeartbeatIntervalMs = 15000;
constexpr int kStaleThresholdMs = 45000;
constexpr int kStaleCheckIntervalMs = 5000;

QString requireStringField(const QJsonObject &object, const QString &key, QString *error)
{
    const QJsonValue value = object.value(key);
    if (!value.isString()) {
        if (error) {
            *error = QString("Realtime payload field '%1' must be a string.").arg(key);
        }
        return {};
    }
    return value.toString();
}

QString optionalStringField(const QJsonObject &object, const QString &key, QString *error)
{
    const QJsonValue value = object.value(key);
    if (value.isUndefined() || value.isNull()) {
        return {};
    }
    if (!value.isString()) {
        if (error) {
            *error = QString("Realtime payload field '%1' must be a string or null.").arg(key);
        }
        return {};
    }
    return value.toString();
}
}

CaseActivityStreamClient::CaseActivityStreamClient(SessionService &session, QObject *parent)
    : ICaseActivityStreamClient(parent)
    , m_session(session)
    , m_socket(new QWebSocket(QString(), QWebSocketProtocol::VersionLatest, this))
    , m_reconnectTimer(new QTimer(this))
    , m_heartbeatTimer(new QTimer(this))
    , m_staleTimer(new QTimer(this))
{
    m_reconnectTimer->setSingleShot(true);
    connect(m_reconnectTimer, &QTimer::timeout, this, [this]() {
        refreshConnection();
    });

    m_heartbeatTimer->setInterval(kHeartbeatIntervalMs);
    connect(m_heartbeatTimer, &QTimer::timeout, this, [this]() {
        if (m_socket->state() == QAbstractSocket::ConnectedState) {
            m_socket->ping(QByteArrayLiteral("case-activity"));
        }
    });

    m_staleTimer->setInterval(kStaleCheckIntervalMs);
    connect(m_staleTimer, &QTimer::timeout, this, [this]() {
        if (m_socket->state() != QAbstractSocket::ConnectedState || !m_lastPongAt.isValid()) {
            return;
        }
        if (m_lastPongAt.elapsed() > kStaleThresholdMs) {
            handleProtocolFailure(QStringLiteral("Realtime websocket stale."));
        }
    });

    connect(m_socket, &QWebSocket::connected, this, [this]() {
        m_reconnectAttempt = 0;
        m_lastPongAt.restart();
        m_heartbeatTimer->start();
        m_staleTimer->start();
        emitConnectionStateIfChanged();
        sendCurrentSubscription();
    });
    connect(m_socket, &QWebSocket::disconnected, this, [this]() {
        const auto closeCode = m_socket->closeCode();
        const QString closeReason = m_socket->closeReason();
        stopTransportTimers();
        emitConnectionStateIfChanged();

        if (closeCode == QWebSocketProtocol::CloseCodePolicyViolated
            && closeReason.contains(QStringLiteral("expired"), Qt::CaseInsensitive)) {
            emit sessionExpired();
        }

        if (shouldMaintainConnection()) {
            scheduleReconnect();
        }
    });
    connect(m_socket, &QWebSocket::textMessageReceived, this, &CaseActivityStreamClient::handleTextMessage);
    connect(m_socket, &QWebSocket::pong, this, [this](quint64, const QByteArray &) {
        m_lastPongAt.restart();
    });
    connect(m_socket, &QWebSocket::errorOccurred, this, [this](QAbstractSocket::SocketError) {
        if (m_socket->state() != QAbstractSocket::ConnectedState && shouldMaintainConnection()) {
            scheduleReconnect();
        }
    });
}

void CaseActivityStreamClient::refreshConnection()
{
    const QUrl desiredUrl = buildDesiredUrl();
    if (!desiredUrl.isValid()) {
        stopReconnect();
        stopTransportTimers();
        m_activeUrl = {};
        if (m_socket->state() == QAbstractSocket::ConnectingState
            || m_socket->state() == QAbstractSocket::ConnectedState) {
            m_socket->close();
        }
        emitConnectionStateIfChanged();
        return;
    }

    if (m_socket->state() == QAbstractSocket::ConnectedState) {
        if (desiredUrl == m_activeUrl) {
            sendCurrentSubscription();
            return;
        }
        m_activeUrl = desiredUrl;
        m_socket->close();
        return;
    }

    if (m_socket->state() == QAbstractSocket::ConnectingState) {
        if (desiredUrl == m_activeUrl) {
            return;
        }
        m_activeUrl = desiredUrl;
        m_socket->abort();
    }

    openSocket(desiredUrl);
}

void CaseActivityStreamClient::subscribeToCase(const QString &caseId, const QString &jobId)
{
    m_caseId = caseId;
    m_jobId = jobId;
    if (m_socket->state() == QAbstractSocket::ConnectedState) {
        sendCurrentSubscription();
        return;
    }
    refreshConnection();
}

void CaseActivityStreamClient::clearSubscription()
{
    if (m_socket->state() == QAbstractSocket::ConnectedState && !m_caseId.isEmpty()) {
        const QJsonObject payload{{"type", "unsubscribe"}};
        m_socket->sendTextMessage(QString::fromUtf8(
            QJsonDocument(payload).toJson(QJsonDocument::Compact)));
    }
    m_caseId.clear();
    m_jobId.clear();
}

void CaseActivityStreamClient::close()
{
    stopReconnect();
    stopTransportTimers();
    m_caseId.clear();
    m_jobId.clear();
    m_reconnectAttempt = 0;
    if (m_socket->state() == QAbstractSocket::ConnectedState
        || m_socket->state() == QAbstractSocket::ConnectingState) {
        m_socket->abort();
    }
    emitConnectionStateIfChanged();
}

bool CaseActivityStreamClient::isConnected() const
{
    return m_socket->state() == QAbstractSocket::ConnectedState;
}

QUrl CaseActivityStreamClient::buildDesiredUrl() const
{
    const QString token = m_session.token();
    const QString baseUrl = ApiService::globalBaseUrl().trimmed();
    if (token.isEmpty() || baseUrl.isEmpty()) {
        return {};
    }

    QUrl url(baseUrl + QStringLiteral("/ws/case-activity"));
    if (!url.isValid() || url.scheme().isEmpty()) {
        return {};
    }

    if (url.scheme() == QStringLiteral("http")) {
        url.setScheme(QStringLiteral("ws"));
    } else if (url.scheme() == QStringLiteral("https")) {
        url.setScheme(QStringLiteral("wss"));
    }

    QUrlQuery query;
    query.addQueryItem(QStringLiteral("token"), token);
    url.setQuery(query);
    return url;
}

bool CaseActivityStreamClient::shouldMaintainConnection() const
{
    return buildDesiredUrl().isValid();
}

void CaseActivityStreamClient::openSocket(const QUrl &url)
{
    stopReconnect();
    m_activeUrl = url;
    m_socket->open(url);
}

void CaseActivityStreamClient::scheduleReconnect()
{
    if (!shouldMaintainConnection()) {
        stopReconnect();
        return;
    }

    if (m_reconnectTimer->isActive()) {
        return;
    }

    const int delayMs = qMin(
        kReconnectInitialDelayMs * (1 << qMin(m_reconnectAttempt, 4)),
        kReconnectMaxDelayMs);
    ++m_reconnectAttempt;
    m_reconnectTimer->start(delayMs);
}

void CaseActivityStreamClient::stopReconnect()
{
    if (m_reconnectTimer->isActive()) {
        m_reconnectTimer->stop();
    }
}

void CaseActivityStreamClient::stopTransportTimers()
{
    m_heartbeatTimer->stop();
    m_staleTimer->stop();
    m_lastPongAt.invalidate();
}

void CaseActivityStreamClient::emitConnectionStateIfChanged()
{
    const bool connected = (m_socket->state() == QAbstractSocket::ConnectedState);
    if (connected == m_reportedConnected) {
        return;
    }
    m_reportedConnected = connected;
    emit connectionStateChanged(connected);
}

void CaseActivityStreamClient::sendCurrentSubscription()
{
    if (m_socket->state() != QAbstractSocket::ConnectedState || m_caseId.isEmpty()) {
        return;
    }

    QJsonObject payload{
        {"type", "subscribe"},
        {"caseId", m_caseId},
    };
    if (!m_jobId.isEmpty()) {
        payload.insert(QStringLiteral("jobId"), m_jobId);
    }
    m_socket->sendTextMessage(QString::fromUtf8(
        QJsonDocument(payload).toJson(QJsonDocument::Compact)));
}

void CaseActivityStreamClient::handleTextMessage(const QString &message)
{
    QJsonParseError parseError;
    const QJsonDocument document = QJsonDocument::fromJson(message.toUtf8(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        handleProtocolFailure(QStringLiteral("Invalid realtime payload."));
        return;
    }

    const QJsonObject object = document.object();
    QString error;
    const QString type = requireStringField(object, QStringLiteral("type"), &error);
    if (!error.isEmpty()) {
        handleProtocolFailure(error);
        return;
    }

    const QString caseId = requireStringField(object, QStringLiteral("caseId"), &error);
    if (!error.isEmpty()) {
        handleProtocolFailure(error);
        return;
    }

    if (type == QStringLiteral("job_status_changed") || type == QStringLiteral("job_completed")) {
        const QString jobId = requireStringField(object, QStringLiteral("jobId"), &error);
        const QString status = requireStringField(object, QStringLiteral("status"), &error);
        if (!error.isEmpty()) {
            handleProtocolFailure(error);
            return;
        }
        emit jobStatusChanged(caseId, jobId, status);
        return;
    }

    if (type == QStringLiteral("image_status_changed")) {
        const QString imageId = requireStringField(object, QStringLiteral("imageId"), &error);
        const QString status = requireStringField(object, QStringLiteral("status"), &error);
        const QString jobId = optionalStringField(object, QStringLiteral("jobId"), &error);
        if (!error.isEmpty()) {
            handleProtocolFailure(error);
            return;
        }
        emit imageStatusChanged(caseId, imageId, status, jobId);
        return;
    }

    handleProtocolFailure(QStringLiteral("Unsupported realtime event type."));
}

void CaseActivityStreamClient::handleProtocolFailure(const QString &reason)
{
    stopTransportTimers();
    if (m_socket->state() == QAbstractSocket::ConnectedState
        || m_socket->state() == QAbstractSocket::ConnectingState) {
        m_socket->abort();
    }
    if (shouldMaintainConnection()) {
        scheduleReconnect();
    }
    Q_UNUSED(reason);
}
