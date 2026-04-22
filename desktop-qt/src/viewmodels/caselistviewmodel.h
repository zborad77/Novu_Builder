#pragma once

#include <QObject>
#include <QString>
#include <vector>

#include "dto/casedto.h"

class ApiService;
class SessionService;

class CaseListViewModel : public QObject
{
    Q_OBJECT
public:
    explicit CaseListViewModel(SessionService &session, QObject *parent = nullptr);

    void loadCases();
    void duplicateCase(const QString &caseId, const QString &mode);

signals:
    void loadingChanged(bool loading);
    void casesLoaded(std::vector<CaseDto> cases);
    void caseDuplicated(QString newCaseId);
    void errorOccurred(QString message);
    void sessionExpiredDetected();

private:
    void setLoading(bool v);

    ApiService *m_api = nullptr;
};
