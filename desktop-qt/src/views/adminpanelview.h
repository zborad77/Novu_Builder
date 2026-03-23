#pragma once

#include <QWidget>

class QTabWidget;
class QTableWidget;
class QTextEdit;
class QPushButton;
class QComboBox;
class QLabel;
class QLineEdit;

class AdminPanelView : public QWidget
{
    Q_OBJECT

public:
    explicit AdminPanelView(QWidget *parent = nullptr);

    void refresh();

signals:
    void impersonationStarted(const QString &token, const QString &userFullName,
                              const QString &orgId, const QString &userId);

private:
    void buildUsersTab(QWidget *tab);
    void buildJobsTab(QWidget *tab);
    void buildCompaniesTab(QWidget *tab);
    void buildAuditTab(QWidget *tab);

    void loadUsers();
    void loadJobs();
    void loadCompanies();
    void loadAudit();

    void onResetPassword();
    void onImpersonate();

    QTabWidget *m_tabs = nullptr;

    // Users tab
    QTableWidget *m_usersTable = nullptr;
    QComboBox *m_orgFilter = nullptr;
    QPushButton *m_resetPwBtn = nullptr;
    QPushButton *m_impersonateBtn = nullptr;

    // Jobs tab
    QTableWidget *m_jobsTable = nullptr;
    QComboBox *m_jobStatusFilter = nullptr;

    // Companies tab
    QTableWidget *m_companiesTable = nullptr;

    // Audit tab
    QTableWidget *m_auditTable = nullptr;
    QLineEdit *m_auditActionFilter = nullptr;
    QComboBox *m_auditOrgFilter = nullptr;
};
