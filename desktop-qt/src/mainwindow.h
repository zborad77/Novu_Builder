#pragma once

#include <QMainWindow>

class QStackedWidget;
class QLabel;
class QWidget;
class CaseDetailView;
class CaseListView;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

private:
    QWidget *createWorkspaceShell();
    void syncActiveCaseWorkspace();
    void updateWorkspaceHeader();
    void switchToLoginMode();
    void switchToWorkspaceMode();

    QStackedWidget *m_stack = nullptr;
    CaseListView *m_caseListView = nullptr;
    CaseDetailView *m_caseDetailView = nullptr;
    QLabel *m_workspaceTitleLabel = nullptr;
    QLabel *m_workspaceSubtitleLabel = nullptr;
};
