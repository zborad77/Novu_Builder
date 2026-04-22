#include "adminpanelview.h"

#include <QComboBox>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QTabWidget>
#include <QTableWidget>
#include <QTextEdit>
#include <QVBoxLayout>

#include "dto/adminjobdto.h"
#include "dto/adminuserdto.h"
#include "dto/auditlogdto.h"
#include "dto/companydto.h"
#include "dto/impersonatedto.h"
#include "services/apiservice.h"
#include "services/sessionservice.h"

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
    QPushButton#impersonateBtn {
        background: #2c3e50;
        color: #f5c28b;
        border: none;
        border-radius: 8px;
        padding: 7px 18px;
        font-weight: 600;
    }
    QPushButton#impersonateBtn:hover { background: #1a252f; }
    QPushButton#impersonateBtn:disabled { background: #c8bfb5; color: #fff; }
    QPushButton#secondaryBtn {
        background: #f7efe4;
        color: #314252;
        border: 1px solid #eadcc8;
        border-radius: 8px;
        padding: 7px 18px;
        font-weight: 600;
    }
    QPushButton#secondaryBtn:hover { background: #eadcc8; }
    QComboBox, QLineEdit {
        border: 1px solid #eadcc8;
        border-radius: 8px;
        padding: 6px 10px;
        background: #fff;
        color: #314252;
    }
    QLabel#sectionTitle {
        font-size: 16px;
        font-weight: 700;
        color: #1f2933;
    }
)";

// ─────────────────────────────────────────────────────────────────────────────

AdminPanelView::AdminPanelView(SessionService &session, QWidget *parent)
    : QWidget(parent)
    , m_apiService(new ApiService(session, this))
{
    connect(m_apiService, &ApiService::sessionExpired, this, [this]() {
        emit sessionExpired();
    });

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
    m_tabs->addTab(jobsTab, QString::fromUtf8("Anal\u00fdzy"));

    auto *companiesTab = new QWidget(m_tabs);
    buildCompaniesTab(companiesTab);
    m_tabs->addTab(companiesTab, "Firmy");

    auto *auditTab = new QWidget(m_tabs);
    buildAuditTab(auditTab);
    m_tabs->addTab(auditTab, "Audit trail");

    layout->addWidget(m_tabs);
    setStyleSheet(kStyleSheet);

    connect(m_tabs, &QTabWidget::currentChanged, this, [this](int idx) {
        if (idx == 0) loadUsers();
        else if (idx == 1) loadJobs();
        else if (idx == 2) loadCompanies();
        else if (idx == 3) loadAudit();
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

    m_impersonateBtn = new QPushButton(QString::fromUtf8("Impersonovat"), tab);
    m_impersonateBtn->setObjectName("impersonateBtn");
    m_impersonateBtn->setEnabled(false);
    m_impersonateBtn->setToolTip(QString::fromUtf8(
        "P\u0159ihl\u00e1s\u00ed v\u00e1s jako tento u\u017eivatel po dobu 15 minut. "
        "Vhodn\u00e9 pro reprodukci bug\u016f."));
    toolbar->addWidget(m_impersonateBtn);

    layout->addLayout(toolbar);

    m_usersTable = new QTableWidget(0, 7, tab);
    m_usersTable->setHorizontalHeaderLabels({
        "ID", QString::fromUtf8("Jm\u00e9no"), "Email", "Role",
        "Firma", QString::fromUtf8("Aktivn\u00ed"), "SuperAdmin"
    });
    m_usersTable->horizontalHeader()->setStretchLastSection(false);
    m_usersTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_usersTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_usersTable->horizontalHeader()->setSectionResizeMode(4, QHeaderView::Stretch);
    m_usersTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_usersTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_usersTable->setAlternatingRowColors(true);
    layout->addWidget(m_usersTable);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadUsers);
    connect(m_orgFilter, &QComboBox::currentIndexChanged, this, &AdminPanelView::loadUsers);
    connect(m_usersTable, &QTableWidget::itemSelectionChanged, this, [this]() {
        const bool sel = m_usersTable->currentRow() >= 0;
        m_resetPwBtn->setEnabled(sel);
        // Disable impersonate for superadmins (column 6 = "✓" for superadmin)
        if (sel) {
            const auto *saItem = m_usersTable->item(m_usersTable->currentRow(), 6);
            m_impersonateBtn->setEnabled(saItem && saItem->text() != QString::fromUtf8("\u2713"));
        } else {
            m_impersonateBtn->setEnabled(false);
        }
    });
    connect(m_resetPwBtn, &QPushButton::clicked, this, &AdminPanelView::onResetPassword);
    connect(m_impersonateBtn, &QPushButton::clicked, this, &AdminPanelView::onImpersonate);
}

void AdminPanelView::loadUsers()
{
    const QString orgId = m_orgFilter->currentData().toString();
    m_apiService->fetchAdminUsers(orgId,
        [this, orgId](std::vector<AdminUserDto> users) {
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
            const int idx = m_orgFilter->findData(orgId);
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
                m_usersTable->setItem(row, 5, new QTableWidgetItem(u.isActive
                    ? QString::fromUtf8("\u2713") : QString::fromUtf8("\u2717")));
                m_usersTable->setItem(row, 6, new QTableWidgetItem(u.isSuperAdmin
                    ? QString::fromUtf8("\u2713") : QString()));
            }
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        });
}

void AdminPanelView::onResetPassword()
{
    const int row = m_usersTable->currentRow();
    if (row < 0) return;

    const QString userId   = m_usersTable->item(row, 0)->text();
    const QString userName = m_usersTable->item(row, 1)->text();
    const QString userEmail= m_usersTable->item(row, 2)->text();

    auto *dialog = new QDialog(this);
    dialog->setWindowTitle(QString::fromUtf8("Reset hesla — %1").arg(userName));
    dialog->setMinimumWidth(360);
    auto *form = new QFormLayout(dialog);

    auto *pwEdit  = new QLineEdit(dialog);
    pwEdit->setEchoMode(QLineEdit::Password);
    pwEdit->setPlaceholderText(QString::fromUtf8("Nov\u00e9 heslo (min. 6 znak\u016f)"));

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

    auto *buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, dialog);
    form->addRow(buttons);

    connect(buttons, &QDialogButtonBox::accepted, dialog, [=]() {
        if (pwEdit->text().length() < 6) {
            errorLabel->setText(QString::fromUtf8("Heslo mus\u00ed m\u00edt alespo\u0148 6 znak\u016f."));
            errorLabel->setVisible(true);
            return;
        }
        if (pwEdit->text() != pw2Edit->text()) {
            errorLabel->setText(QString::fromUtf8("Hesla se neshoduj\u00ed."));
            errorLabel->setVisible(true);
            return;
        }
        dialog->accept();
    });
    connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject);

    if (dialog->exec() != QDialog::Accepted) { dialog->deleteLater(); return; }

    const QString newPassword = pwEdit->text();
    dialog->deleteLater();

    m_apiService->resetUserPassword(userId, newPassword,
        [this, userName]() {
            QMessageBox::information(this, QString::fromUtf8("Hotovo"),
                QString::fromUtf8("Heslo pro %1 bylo \u00fasp\u011b\u0161n\u011b zm\u011bn\u011bno.").arg(userName));
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"),
                err.isEmpty() ? QString::fromUtf8("Reset hesla selhal.") : err);
        });
}

void AdminPanelView::onImpersonate()
{
    const int row = m_usersTable->currentRow();
    if (row < 0) return;

    const QString userId   = m_usersTable->item(row, 0)->text();
    const QString userName = m_usersTable->item(row, 1)->text();
    const QString orgName  = m_usersTable->item(row, 4)->text();

    const auto answer = QMessageBox::question(
        this,
        QString::fromUtf8("Impersonovat u\u017eivatele"),
        QString::fromUtf8(
            "Chcete se p\u0159ihl\u00e1sit jako <b>%1</b> (%2)?<br><br>"
            "Token vyprch\u00e1 za 15 minut.<br>"
            "V\u0161echny akce budou zalogov\u00e1ny v audit trailu.")
            .arg(userName, orgName),
        QMessageBox::Yes | QMessageBox::Cancel);

    if (answer != QMessageBox::Yes) return;

    m_apiService->impersonateUser(userId,
        [this](ImpersonateDto dto) {
            emit impersonationStarted(dto.accessToken, dto.userFullName, dto.orgId, dto.userId);
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"),
                err.isEmpty() ? QString::fromUtf8("Impersonace selhala.") : err);
        });
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
    m_apiService->fetchAdminJobs(m_jobStatusFilter->currentData().toString(),
        [this](std::vector<AdminJobDto> jobs) {
            m_jobsTable->setRowCount(0);
            for (const auto &j : jobs) {
                const int row = m_jobsTable->rowCount();
                m_jobsTable->insertRow(row);
                m_jobsTable->setItem(row, 0, new QTableWidgetItem(j.id.left(12) + "..."));
                auto *statusItem = new QTableWidgetItem(j.status);
                if (j.status == "running")   statusItem->setForeground(QColor("#2ecc71"));
                else if (j.status == "failed") statusItem->setForeground(QColor("#e74c3c"));
                else if (j.status == "pending") statusItem->setForeground(QColor("#e07b39"));
                m_jobsTable->setItem(row, 1, statusItem);
                m_jobsTable->setItem(row, 2, new QTableWidgetItem(j.caseTitle));
                m_jobsTable->setItem(row, 3, new QTableWidgetItem(j.orgName));
                m_jobsTable->setItem(row, 4, new QTableWidgetItem(j.jobType));
                m_jobsTable->setItem(row, 5, new QTableWidgetItem(j.startedAt));
                m_jobsTable->setItem(row, 6, new QTableWidgetItem(j.errorMessage));
            }
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        });
}

// ── Companies Tab ─────────────────────────────────────────────────────────────

void AdminPanelView::buildCompaniesTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *toolbar = new QHBoxLayout();
    auto *refreshBtn = new QPushButton(QString::fromUtf8("Obnovit"), tab);
    refreshBtn->setObjectName("secondaryBtn");
    toolbar->addStretch();
    toolbar->addWidget(refreshBtn);
    layout->addLayout(toolbar);

    m_companiesTable = new QTableWidget(0, 6, tab);
    m_companiesTable->setHorizontalHeaderLabels({
        "ID", QString::fromUtf8("N\u00e1zev"), QString::fromUtf8("I\u010cO"),
        "Email", "Tel.", QString::fromUtf8("U\u017eivatel\u016f")
    });
    m_companiesTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    m_companiesTable->horizontalHeader()->setSectionResizeMode(3, QHeaderView::Stretch);
    m_companiesTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_companiesTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_companiesTable->setAlternatingRowColors(true);
    layout->addWidget(m_companiesTable);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadCompanies);
}

void AdminPanelView::loadCompanies()
{
    m_apiService->fetchAdminCompanies(
        [this](std::vector<CompanyDto> companies) {
            m_companiesTable->setRowCount(0);
            for (const auto &c : companies) {
                const int row = m_companiesTable->rowCount();
                m_companiesTable->insertRow(row);
                m_companiesTable->setItem(row, 0, new QTableWidgetItem(c.id));
                m_companiesTable->setItem(row, 1, new QTableWidgetItem(c.name));
                m_companiesTable->setItem(row, 2, new QTableWidgetItem(c.ico));
                m_companiesTable->setItem(row, 3, new QTableWidgetItem(c.email));
                m_companiesTable->setItem(row, 4, new QTableWidgetItem(c.phone));
                m_companiesTable->setItem(row, 5, new QTableWidgetItem(QString::number(c.userCount)));
            }
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        });
}

// ── Audit Tab ─────────────────────────────────────────────────────────────────

void AdminPanelView::buildAuditTab(QWidget *tab)
{
    auto *layout = new QVBoxLayout(tab);
    layout->setContentsMargins(12, 12, 12, 12);
    layout->setSpacing(10);

    auto *toolbar = new QHBoxLayout();

    m_auditOrgFilter = new QComboBox(tab);
    m_auditOrgFilter->addItem(QString::fromUtf8("V\u0161echny firmy"), QString());
    toolbar->addWidget(new QLabel("Firma:", tab));
    toolbar->addWidget(m_auditOrgFilter, 1);

    m_auditActionFilter = new QLineEdit(tab);
    m_auditActionFilter->setPlaceholderText(QString::fromUtf8("Filtr akce (pr. case, auth...)"));
    toolbar->addWidget(m_auditActionFilter, 1);

    auto *refreshBtn = new QPushButton(QString::fromUtf8("Obnovit"), tab);
    refreshBtn->setObjectName("secondaryBtn");
    toolbar->addWidget(refreshBtn);
    layout->addLayout(toolbar);

    m_auditTable = new QTableWidget(0, 7, tab);
    m_auditTable->setHorizontalHeaderLabels({
        QString::fromUtf8("Kdy"), QString::fromUtf8("U\u017eivatel"),
        "Akce", QString::fromUtf8("Typ"), "ID", "Firma", "IP"
    });
    m_auditTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);
    m_auditTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::ResizeToContents);
    m_auditTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_auditTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_auditTable->setAlternatingRowColors(true);
    layout->addWidget(m_auditTable);

    connect(refreshBtn, &QPushButton::clicked, this, &AdminPanelView::loadAudit);
    connect(m_auditActionFilter, &QLineEdit::returnPressed, this, &AdminPanelView::loadAudit);
}

void AdminPanelView::loadAudit()
{
    const QString orgId  = m_auditOrgFilter->currentData().toString();
    const QString action = m_auditActionFilter->text().trimmed();

    m_apiService->fetchAdminAudit(orgId, action, 300,
        [this](std::vector<AuditLogDto> logs) {
            if (m_auditOrgFilter->count() <= 1) {
                m_apiService->fetchAdminCompanies([this](std::vector<CompanyDto> companies) {
                    for (const auto &c : companies) {
                        m_auditOrgFilter->addItem(c.name, c.id);
                    }
                });
            }

            m_auditTable->setRowCount(0);
            for (const auto &a : logs) {
                const int row = m_auditTable->rowCount();
                m_auditTable->insertRow(row);

                QString ts = a.createdAt;
                if (ts.length() > 19) ts = ts.left(19).replace('T', ' ');
                m_auditTable->setItem(row, 0, new QTableWidgetItem(ts));

                QString userLabel = a.userEmail;
                if (!a.impersonatedBy.isEmpty())
                    userLabel += QString::fromUtf8(" \u26a0\ufe0f");
                m_auditTable->setItem(row, 1, new QTableWidgetItem(userLabel));
                m_auditTable->setItem(row, 2, new QTableWidgetItem(a.action));
                m_auditTable->setItem(row, 3, new QTableWidgetItem(a.resourceType));
                m_auditTable->setItem(row, 4, new QTableWidgetItem(a.resourceId));
                m_auditTable->setItem(row, 5, new QTableWidgetItem(a.orgId));
                m_auditTable->setItem(row, 6, new QTableWidgetItem(a.ip));

                if (!a.impersonatedBy.isEmpty()) {
                    for (int col = 0; col < 7; ++col) {
                        if (auto *item = m_auditTable->item(row, col))
                            item->setBackground(QColor("#fff3cd"));
                    }
                }
            }
        },
        [this](const QString &err) {
            QMessageBox::warning(this, QString::fromUtf8("Chyba"), err);
        });
}

void AdminPanelView::refresh()
{
    const int idx = m_tabs->currentIndex();
    if (idx == 0) loadUsers();
    else if (idx == 1) loadJobs();
    else if (idx == 2) loadCompanies();
    else if (idx == 3) loadAudit();
}
