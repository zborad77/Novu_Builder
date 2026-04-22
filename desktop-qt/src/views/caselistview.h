#pragma once

#include <vector>

#include <QWidget>

#include "dto/casedto.h"

class CaseListViewModel;
class QLabel;
class QPushButton;
class SessionService;

class CaseListView : public QWidget
{
    Q_OBJECT

public:
    explicit CaseListView(SessionService &session, QWidget *parent = nullptr);
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
    void onCasesLoaded(std::vector<CaseDto> cases);
    void onCaseLoadError(const QString &message);

    [[nodiscard]] bool isHistoryCase(const CaseDto &caseDto) const;
    [[nodiscard]] bool isWorkCase(const CaseDto &caseDto) const;
    QPushButton *createOptionButton(const QString &label, const QString &optionKey, QWidget *parent);

    CaseListViewModel *m_viewModel = nullptr;
    QLabel *m_errorLabel = nullptr;
    std::vector<CaseDto> m_cases;
    QString m_currentCaseId;
    QString m_pendingPreferredCaseId;
    bool m_pendingEmitSignal = false;
    QList<QPushButton *> m_fieldButtons;
    QPushButton *m_editCaseButton = nullptr;
    bool m_fieldButtonsExpanded = false;
};
