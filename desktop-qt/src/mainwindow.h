#pragma once

#include <QMainWindow>

#include "services/sessionservice.h"

class QFrame;
class QStackedWidget;
class QLabel;
class QPushButton;
class QWidget;
class AdminPanelView;
class CaseBrowserView;
class CaseDetailView;
class CaseListView;
class LoginView;
class NewCaseView;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

private:
    void handleLoginRequested(const QString &email, const QString &password);
    void handleSessionExpired();
    void openServerSetupDialog(bool firstTime = false);
    QWidget *createWorkspaceShell();
    void syncActiveCaseWorkspace();
    void updateWorkspaceHeader();
    void switchToLoginMode();
    void switchToWorkspaceMode();
    void showWelcomeView();
    void showNewCaseView();
    void showCaseDetailView();
    void showAdminPanelView();
    void startImpersonation(const QString &token, const QString &userFullName,
                            const QString &orgId, const QString &userId);
    void stopImpersonation();
    void setSidebarActiveSection(QPushButton *activeButton);
    bool confirmNavigateAway();

    SessionService m_session;
    QStackedWidget *m_stack = nullptr;
    LoginView *m_loginView = nullptr;
    CaseListView *m_caseListView = nullptr;
    CaseDetailView *m_caseDetailView = nullptr;
    NewCaseView *m_newCaseView = nullptr;
    CaseBrowserView *m_caseBrowserView = nullptr;
    AdminPanelView *m_adminPanelView = nullptr;
    QStackedWidget *m_detailStack = nullptr;
    QWidget *m_welcomeView = nullptr;
    QFrame *m_caseColumn = nullptr;
    QLabel *m_workspaceTitleLabel = nullptr;
    QLabel *m_workspaceSubtitleLabel = nullptr;
    QPushButton *m_sidebarServerCasesButton = nullptr;
    QPushButton *m_sidebarWorkCasesButton = nullptr;
    QPushButton *m_sidebarHistoryButton = nullptr;
    QPushButton *m_sidebarNewCaseButton = nullptr;
    QPushButton *m_sidebarAdminButton = nullptr;
    QPushButton *m_serverButton = nullptr;
    QString m_caseListSection; // "Rozpracované zakázky" | "Historie zakázek"

    // Impersonation
    QString m_savedAdminToken;
    QFrame *m_impersonationBanner = nullptr;
    QLabel *m_impersonationLabel = nullptr;
    QPushButton *m_stopImpersonationBtn = nullptr;
};
