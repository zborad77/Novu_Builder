#pragma once

#include <QObject>
#include <QString>

class ICaseActivityStreamClient : public QObject
{
    Q_OBJECT
public:
    explicit ICaseActivityStreamClient(QObject *parent = nullptr) : QObject(parent) {}
    ~ICaseActivityStreamClient() override = default;

    virtual void subscribeToCase(const QString &caseId, const QString &jobId = QString()) = 0;
    virtual void clearSubscription() = 0;
    [[nodiscard]] virtual bool isConnected() const = 0;

signals:
    void connectionStateChanged(bool connected);
    void jobStatusChanged(QString caseId, QString jobId, QString status);
    void imageStatusChanged(QString caseId, QString imageId, QString status, QString jobId);
    void sessionExpired();
};
