#include "adminpanelview.h"

#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QInputDialog>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QTabWidget>
#include <QTableWidget>
#include <QTextEdit>
#include <QVBoxLayout>

#include "services/apiservice.h"

static const QString kStyleSheet = R"(
    QTabWidget::pane {
        border: 1px solid #eadcc8;
        border-radius: 10px;
        background: #fffaf2;
    }
    QTabBar::tab {
        background: #f7efe4;
        border: 1px solid #eadcc8;
        border-bottom: none;
        padding: 8px 18px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        font-weight: 600;
        color: #314252;
    }
    QTabBar::tab:selected {
        background: #fffaf2;
        color: #e07b39;
    }
    QTableWidget {
        border: none;
        background: transparent;
        gridline-color: #eadcc8;
        font-size: 13px;
    }
    QHeaderView::section {
        background: #f7efe4;
        border: none;
        border-bottom: 1px solid #eadcc8;
        padding: 6px 10px;
        font-weight: 700;
        color: #314252;
    }
    QPushButton#actionBtn {
        background: #e07b39;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 7px 18px;
        font-weight: 600;
    }
    QPushButton#actionBtn:hover { background: #c96a2c; }
    QPushButton#actionBtn:disabled { background: #c8bfb5; }
    QPushButton#secondaryBtn {
        background: #f7efe4;
        color: #314252;
        border: 1px solid #eadcc8;
        border-radius: 8px;
        padding: 7px 18px;
        font-weight: 600;
    }
    QPushButton#secondaryBtn:hover { background: #eadcc8; }
    QComboBox {
        border: 1px solid #eadcc8;
        border-radius: 8px;
        padding: 6px 10px;
        background: #fff;
        color: #314252;
    }
    QTextEdit {
        border: 1px solid #eadcc8;
        border-radius: 8px;
        background: #1e1e2e;
        color: #cdd6f4;
        font-family: monospace;
        font-size: 12px;
    }
    QLabel#sectionTitle {
        font-size: 16px;
        font-weight: 700;
        color: #1f2933;
    }
)";

// ─────────────────────────────────────────────────────────────────────────────

AdminPanelView::AdminPanelView(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(12);

    auto *title = new QLabel(QString::fromUtf8("Spr\u00e1va serveru"), this);
    title->setObjectName("sectionTitle");
    layout->addWidget(title);

    m_tabs = new QTabWidget(this);

    auto *usersTab = new QWidget(m_tabs);
    buildUsersTab(usersTab);
    m_tabs->addTab(usersTab, QString::fromUtf8("U\u017eivatel\u00e9"));

    auto *jobsTab = new QWidget(m_tabs);
    buildJobsTab(jobsTab);
    m_tabs->addTab(jobsTab, "Anal\u00fdzy (jobs)");

    auto *logsTab = new QWidget(m_tabs);
    buildLogsTab(logsTab);
    m_tabs->addTab(logsTab, "Logy");

    layout->addWidget(m_tabs);

    setStyleSheet(kStyleSheet);

    connect(m_tabs, &QTabWidget::currentChanged, this, [this](int idx) {
        if (idx == 0) loadUsers();
        else if (idx == 1) loadJobs();
        else if (idx == 2) loadLogs();
    });
}

// ── Users Tab ─────────────────────────────────────────────────────────────────

void AdminPanelView::buildUsersTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *toolbar = new QHBoxLayout();

    auto *filterLabel = new QLabel(QString::fromUtf8("Filtr firmy:"), tab);
    m_orgFilter = new QComboBox(tab);
    m_orgFilter->addItem(QString::fromUtf8("V\u0161echny firmy"), QString());
    toolbar->addWidget(filterLabel);
    toolbar->addWidget(m_orgFilter, 1);

    auto *refreshBtn = new QPushButton(QString::fromUtf8("Obnovit"), tab);
    refreshBtn->setObjectName("secondaryBtn");
    toolbar->addWidget(refreshBtn);

    m_resetPwBtn = new QPushButton(QString::fromUtf8("Reset hesla"), tab);
    m_resetPwBtn->setObjectName("actionBtn");
    m_resetPwBtn->setEnabled(false);
    toolbar->addWidget(m_resetPwBtn);

    layout->addLayout(toolbar);

    m_usersTable = new QTableWidget(0, 6, tab);
    m_usersTable->setHorizontalHeaderLabels({
        "ID", QString::fromUtf8("Jm\u00e9no"), "Email", "Role",
        QString::fromUtf8("Firma"), QString::fromUtf8("Aktivn\u00ed")
    });
    m_usersTable->horizontalHeader()->setStretchLastSection(true);
    m_usersTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_usersTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_usersTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_usersTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_usersTable->setAlternatingRowColors(true);
    layout->addWidget(m_usersTable);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadUsers);
    connect(m_orgFilter, &QComboBox::currentIndexChanged, this, &AdminPanelView::loadUsers);
    connect(m_usersTable, &QTableWidget::itemSelectionChanged, this, [this]() {
        m_resetPwBtn->setEnabled(m_usersTable->currentRow() >= 0);
    });
    connect(m_resetPwBtn, &QPushButton::clicked, this, &AdminPanelView::onResetPassword);
}

void AdminPanelView::loadUsers()
{
    ApiService api;
    QString err;
    const QString orgId = m_orgFilter->currentData().toString();
    const auto users = api.fetchAdminUsers(orgId, &err);

    if (!err.isEmpty()) {
        QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        return;
    }

    // Repopulate org filter from data (keep current selection)
    const QString currentOrg = m_orgFilter->currentData().toString();
    m_orgFilter->blockSignals(true);
    m_orgFilter->clear();
    m_orgFilter->addItem(QString::fromUtf8("V\u0161echny firmy"), QString());
    QStringList seenOrgs;
    for (const auto &u : users) {
        if (!u.orgId.isEmpty() && !seenOrgs.contains(u.orgId)) {
            seenOrgs.append(u.orgId);
            m_orgFilter->addItem(u.orgName.isEmpty() ? u.orgId : u.orgName, u.orgId);
        }
    }
    const int idx = m_orgFilter->findData(currentOrg);
    if (idx >= 0) m_orgFilter->setCurrentIndex(idx);
    m_orgFilter->blockSignals(false);

    m_usersTable->setRowCount(0);
    for (const auto &u : users) {
        const int row = m_usersTable->rowCount();
        m_usersTable->insertRow(row);
        m_usersTable->setItem(row, 0, new QTableWidgetItem(u.id));
        m_usersTable->setItem(row, 1, new QTableWidgetItem(u.fullName));
        m_usersTable->setItem(row, 2, new QTableWidgetItem(u.email));
        m_usersTable->setItem(row, 3, new QTableWidgetItem(u.role));
        m_usersTable->setItem(row, 4, new QTableWidgetItem(u.orgName));
        m_usersTable->setItem(row, 5, new QTableWidgetItem(u.isActive ? "✓" : "✗"));
    }
}

void AdminPanelView::onResetPassword()
{
    const int row = m_usersTable->currentRow();
    if (row < 0) return;

    const QString userId = m_usersTable->item(row, 0)->text();
    const QString userName = m_usersTable->item(row, 1)->text();
    const QString userEmail = m_usersTable->item(row, 2)->text();

    // Dialog se dvěma poli pro nové heslo + potvrzení
    auto *dialog = new QDialog(this);
    dialog->setWindowTitle(QString::fromUtf8("Reset hesla — %1").arg(userName));
    dialog->setMinimumWidth(360);
    auto *form = new QFormLayout(dialog);

    auto *pwEdit = new QLineEdit(dialog);
    pwEdit->setEchoMode(QLineEdit::Password);
    pwEdit->setPlaceholderText(QString::fromUtf8("Nove heslo (min. 6 znaku)"));

    auto *pw2Edit = new QLineEdit(dialog);
    pw2Edit->setEchoMode(QLineEdit::Password);
    pw2Edit->setPlaceholderText(QString::fromUtf8("Potvrdit heslo"));

    auto *errorLabel = new QLabel(dialog);
    errorLabel->setStyleSheet("color: #c0392b; font-size: 12px;");
    errorLabel->setVisible(false);

    form->addRow("Email:", new QLabel(userEmail, dialog));
    form->addRow(QString::fromUtf8("Nov\u00e9 heslo:"), pwEdit);
    form->addRow(QString::fromUtf8("Potvrzen\u00ed:"), pw2Edit);
    form->addRow(errorLabel);

    auto *buttons = new QDialogButtonBox(
        QDialogButtonBox::Ok | QDialogButtonBox::Cancel, dialog);
    form->addRow(buttons);

    connect(buttons, &QDialogButtonBox::accepted, dialog, [=]() {
        const QString pw = pwEdit->text();
        const QString pw2 = pw2Edit->text();
        if (pw.length() < 6) {
            errorLabel->setText(QString::fromUtf8("Heslo mus\u00ed m\u00edt alespo\u0148 6 znak\u016f."));
            errorLabel->setVisible(true);
            return;
        }
        if (pw != pw2) {
            errorLabel->setText(QString::fromUtf8("Hesla se neshoduj\u00ed."));
            errorLabel->setVisible(true);
            return;
        }
        dialog->accept();
    });
    connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);

    if (dialog->exec() != QDialog::Accepted) {
        dialog->deleteLater();
        return;
    }

    const QString newPassword = pwEdit->text();
    dialog->deleteLater();

    ApiService api;
    QString err;
    const bool ok = api.resetUserPassword(userId, newPassword, &err);
    if (!ok) {
        QMessageBox::warning(this, QString::fromUtf8("Chyba"), err.isEmpty()
            ? QString::fromUtf8("Reset hesla selhal.") : err);
        return;
    }
    QMessageBox::information(this, QString::fromUtf8("Hotovo"),
        QString::fromUtf8("Heslo pro %1 bylo \u00fasp\u011b\u0161n\u011b zm\u011bn\u011bno.").arg(userName));
}

// ── Jobs Tab ──────────────────────────────────────────────────────────────────

void AdminPanelView::buildJobsTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *toolbar = new QHBoxLayout();

    auto *filterLabel = new QLabel("Status:", tab);
    m_jobStatusFilter = new QComboBox(tab);
    m_jobStatusFilter->addItem(QString::fromUtf8("V\u0161echny"), QString());
    m_jobStatusFilter->addItem("pending", "pending");
    m_jobStatusFilter->addItem("running", "running");
    m_jobStatusFilter->addItem("completed", "completed");
    m_jobStatusFilter->addItem("failed", "failed");
    toolbar->addWidget(filterLabel);
    toolbar->addWidget(m_jobStatusFilter, 1);

    auto *refreshBtn = new QPushButton(QString::fromUtf8("Obnovit"), tab);
    refreshBtn->setObjectName("secondaryBtn");
    toolbar->addWidget(refreshBtn);
    layout->addLayout(toolbar);

    m_jobsTable = new QTableWidget(0, 7, tab);
    m_jobsTable->setHorizontalHeaderLabels({
        "ID", "Status", QString::fromUtf8("Zak\u00e1zka"), "Firma",
        "Typ", QString::fromUtf8("Spu\u0161t\u011bno"), "Chyba"
    });
    m_jobsTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_jobsTable->horizontalHeader()->setSectionResizeMode(6, QHeaderView::Stretch);
    m_jobsTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_jobsTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_jobsTable->setAlternatingRowColors(true);
    layout->addWidget(m_jobsTable);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadJobs);
    connect(m_jobStatusFilter, &QComboBox::currentIndexChanged, this, &AdminPanelView::loadJobs);
}

void AdminPanelView::loadJobs()
{
    ApiService api;
    QString err;
    const QString statusFilter = m_jobStatusFilter->currentData().toString();
    const auto jobs = api.fetchAdminJobs(statusFilter, &err);

    if (!err.isEmpty()) {
        QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        return;
    }

    m_jobsTable->setRowCount(0);
    for (const auto &j : jobs) {
        const int row = m_jobsTable->rowCount();
        m_jobsTable->insertRow(row);
        m_jobsTable->setItem(row, 0, new QTableWidgetItem(j.id.left(12) + "..."));
        auto *statusItem = new QTableWidgetItem(j.status);
        if (j.status == "running") statusItem->setForeground(QColor("#2ecc71"));
        else if (j.status == "failed") statusItem->setForeground(QColor("#e74c3c"));
        else if (j.status == "pending") statusItem->setForeground(QColor("#e07b39"));
        m_jobsTable->setItem(row, 1, statusItem);
        m_jobsTable->setItem(row, 2, new QTableWidgetItem(j.caseTitle));
        m_jobsTable->setItem(row, 3, new QTableWidgetItem(j.orgName));
        m_jobsTable->setItem(row, 4, new QTableWidgetItem(j.jobType));
        m_jobsTable->setItem(row, 5, new QTableWidgetItem(j.startedAt));
        m_jobsTable->setItem(row, 6, new QTableWidgetItem(j.errorMessage));
    }
}

// ── Logs Tab ──────────────────────────────────────────────────────────────────

void AdminPanelView::buildLogsTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *toolbar = new QHBoxLayout();

    m_logStatusLabel = new QLabel(QString::fromUtf8("Posledn\u00edch 200 \u0159\u00e1dk\u016f logu"), tab);
    toolbar->addWidget(m_logStatusLabel, 1);

    auto *refreshBtn = new QPushButton(QString::fromUtf8("Obnovit"), tab);
    refreshBtn->setObjectName("secondaryBtn");
    toolbar->addWidget(refreshBtn);
    layout->addLayout(toolbar);

    m_logView = new QTextEdit(tab);
    m_logView->setReadOnly(true);
    layout->addWidget(m_logView);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadLogs);
}

void AdminPanelView::loadLogs()
{
    ApiService api;
    QString err;
    const QString logs = api.fetchAdminLogs(200, &err);

    if (!err.isEmpty()) {
        m_logView->setPlainText(QString::fromUtf8("Chyba: ") + err);
        return;
    }

    m_logView->setPlainText(logs);
    // Scroll to bottom (nejnovější záznamy dole)
    auto *scrollBar = m_logView->verticalScrollBar();
    scrollBar->setValue(scrollBar->maximum());
    m_logStatusLabel->setText(QString::fromUtf8("Posledn\u00edch 200 \u0159\u00e1dk\u016f — obnoveno"));
}

void AdminPanelView::refresh()
{
    const int idx = m_tabs->currentIndex();
    if (idx == 0) loadUsers();
    else if (idx == 1) loadJobs();
    else if (idx == 2) loadLogs();
}
