#include "caselistviewmodel.h"

#include "services/apiservice.h"
#include "services/sessionservice.h"

CaseListViewModel::CaseListViewModel(SessionService &session, QObject *parent)
    : QObject(parent)
    , m_api(new ApiService(session, this))
{
    connect(m_api, &ApiService::sessionExpired, this, [this]() {
        emit sessionExpiredDetected();
    });
}

void CaseListViewModel::setLoading(bool v)
{
    emit loadingChanged(v);
}

void CaseListViewModel::loadCases()
{
    setLoading(true);
    m_api->fetchCases(
        [this](std::vector<CaseDto> cases) {
            setLoading(false);
            emit casesLoaded(std::move(cases));
        },
        [this](const QString &err) {
            setLoading(false);
            emit errorOccurred(err);
        });
}

void CaseListViewModel::duplicateCase(const QString &caseId, const QString &mode)
{
    setLoading(true);
    m_api->duplicateCase(caseId, mode,
        [this](const QString &newId) {
            setLoading(false);
            emit caseDuplicated(newId);
        },
        [this](const QString &err) {
            setLoading(false);
            emit errorOccurred(err);
        });
}
