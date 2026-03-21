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
    void setCurrentCaseId(const QString &caseId, bool emitSignal);
    void updateForCaseSource(const QString &source);

signals:
    void caseSelected(const QString &caseId);
    void optionRequested(const QString &optionKey);
    void sessionExpired();

private:
    [[nodiscard]] bool isHistoryCase(const CaseDto &caseDto) const;
    [[nodiscard]] bool isWorkCase(const CaseDto &caseDto) const;
    QPushButton *createOptionButton(const QString &label, const QString &optionKey, QWidget *parent);

    QLabel *m_errorLabel = nullptr;
    std::vector<CaseDto> m_cases;
    QString m_currentCaseId;
    QList<QPushButton *> m_fieldButtons;  // shown for desktop cases, or expanded under edit button
    QPushButton *m_editCaseButton = nullptr; // shown for mobile cases (toggles field buttons)
    bool m_fieldButtonsExpanded = false;
};
