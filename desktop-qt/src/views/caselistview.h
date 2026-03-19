#pragma once

#include <vector>

#include <QWidget>

#include "dto/casedto.h"

class QLabel;
class QPushButton;

class CaseListView : public QWidget
{
    Q_OBJECT

public:
    explicit CaseListView(QWidget *parent = nullptr);
    [[nodiscard]] QString currentCaseId() const;
    [[nodiscard]] QString currentCaseTitle() const;
    [[nodiscard]] bool currentCaseIsReferenceDataset() const;
    void reloadCases(const QString &preferredCurrentCaseId = QString(), bool emitSignal = false);

signals:
    void caseSelected(const QString &caseId);
    void optionRequested(const QString &optionKey);

private:
    [[nodiscard]] bool isHistoryCase(const CaseDto &caseDto) const;
    [[nodiscard]] bool isWorkCase(const CaseDto &caseDto) const;
    void setCurrentCaseId(const QString &caseId, bool emitSignal);
    QPushButton *createOptionButton(const QString &label, const QString &optionKey, QWidget *parent);

    QLabel *m_errorLabel = nullptr;
    std::vector<CaseDto> m_cases;
    QString m_currentCaseId;
};
