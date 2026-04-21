#pragma once

#include <QList>
#include <QObject>
#include <QString>
#include <QStringList>

#include "dto/casedto.h"

class AiDetectionWorkItemCoordinator : public QObject
{
    Q_OBJECT

public:
    explicit AiDetectionWorkItemCoordinator(QObject *parent = nullptr);

    void setCaseData(const CaseDto &caseData);
    void setSelectedOverlayIds(const QList<QString> &overlayIds);
    void reset();

signals:
    void mappingChanged(const QList<QString> &overlayIds,
                        const QString &summary,
                        const QStringList &mappedItems,
                        bool highlightsProposalItems);

private:
    void recompute();
    static QString localizeRecommendedScope(const QString &scope);

    CaseDto        m_caseData;
    QString        m_currentCaseId;       // canonical guard for async fetch completion
    QList<QString> m_selectedOverlayIds;
};
