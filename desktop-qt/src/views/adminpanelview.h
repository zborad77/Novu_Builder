#pragma once

#include <QWidget>

class QTabWidget;
class QTableWidget;
class QTextEdit;
class QPushButton;
class QComboBox;
class QLabel;

class AdminPanelView : public QWidget
{
    Q_OBJECT

public:
    explicit AdminPanelView(QWidget *parent = nullptr);

    void refresh();

private:
    void buildUsersTab(QWidget *tab);
    void buildJobsTab(QWidget *tab);
    void buildLogsTab(QWidget *tab);

    void loadUsers();
    void loadJobs();
    void loadLogs();

    void onResetPassword();

    QTabWidget *m_tabs = nullptr;

    // Users tab
    QTableWidget *m_usersTable = nullptr;
    QComboBox *m_orgFilter = nullptr;
    QPushButton *m_resetPwBtn = nullptr;

    // Jobs tab
    QTableWidget *m_jobsTable = nullptr;
    QComboBox *m_jobStatusFilter = nullptr;

    // Logs tab
    QTextEdit *m_logView = nullptr;
    QLabel *m_logStatusLabel = nullptr;
};
