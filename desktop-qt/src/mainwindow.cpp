#include "mainwindow.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QStackedWidget>
#include <QStatusBar>
#include <QVBoxLayout>

#include "views/casedetailview.h"
#include "views/caselistview.h"
#include "views/loginview.h"

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle("FotoNabidka Desktop");

    m_stack = new QStackedWidget(this);
    auto *loginView = new LoginView(this);
    m_stack->addWidget(loginView);
    m_stack->addWidget(createWorkspaceShell());
    m_stack->setCurrentIndex(0);

    setCentralWidget(m_stack);
    switchToLoginMode();

    connect(loginView, &LoginView::loginRequested, this, [this](const QString &, const QString &) {
        m_stack->setCurrentIndex(1);
        switchToWorkspaceMode();
    });
}

QWidget *MainWindow::createWorkspaceShell()
{
    auto *workspace = new QWidget(this);
    auto *rootLayout = new QHBoxLayout(workspace);
    rootLayout->setContentsMargins(0, 0, 0, 0);
    rootLayout->setSpacing(0);

    auto *sidebar = new QFrame(workspace);
    sidebar->setFixedWidth(220);
    sidebar->setObjectName("sidebar");

    auto *sidebarLayout = new QVBoxLayout(sidebar);
    sidebarLayout->setContentsMargins(18, 18, 18, 18);
    sidebarLayout->setSpacing(12);

    auto *brand = new QLabel("NOVU", sidebar);
    brand->setObjectName("brandLabel");
    sidebarLayout->addWidget(brand);

    auto *projectButton = new QPushButton("Projekt", sidebar);
    projectButton->setEnabled(false);
    auto *workCasesButton = new QPushButton("Rozpracovane zakazky", sidebar);
    auto *historyButton = new QPushButton("Historie zakazek", sidebar);
    auto *loginButton = new QPushButton("Login view", sidebar);
    sidebarLayout->addWidget(projectButton);
    sidebarLayout->addWidget(workCasesButton);
    sidebarLayout->addWidget(historyButton);
    sidebarLayout->addStretch();
    sidebarLayout->addWidget(loginButton);

    auto *content = new QWidget(workspace);
    auto *contentLayout = new QVBoxLayout(content);
    contentLayout->setContentsMargins(24, 20, 24, 24);
    contentLayout->setSpacing(18);

    auto *header = new QFrame(content);
    header->setObjectName("headerCard");
    auto *headerLayout = new QHBoxLayout(header);
    headerLayout->setContentsMargins(20, 16, 20, 16);

    auto *titleColumn = new QVBoxLayout();
    m_workspaceTitleLabel = new QLabel("Zatim neni aktivni zakazka", header);
    m_workspaceTitleLabel->setObjectName("pageTitle");
    m_workspaceSubtitleLabel = new QLabel(
        "Tady bude vzdy otevrena hlavni pracovni karta aktualni zakazky.",
        header);
    m_workspaceSubtitleLabel->setWordWrap(true);
    m_workspaceSubtitleLabel->setObjectName("subtitleLabel");
    titleColumn->addWidget(m_workspaceTitleLabel);
    titleColumn->addWidget(m_workspaceSubtitleLabel);

    auto *statusChip = new QLabel("Desktop v1", header);
    statusChip->setObjectName("statusChip");

    headerLayout->addLayout(titleColumn, 1);
    headerLayout->addWidget(statusChip, 0, Qt::AlignTop);

    auto *body = new QHBoxLayout();
    body->setSpacing(18);

    auto *caseColumn = new QFrame(content);
    caseColumn->setObjectName("panelCard");
    auto *caseColumnLayout = new QVBoxLayout(caseColumn);
    caseColumnLayout->setContentsMargins(0, 0, 0, 0);
    m_caseListView = new CaseListView(caseColumn);
    caseColumnLayout->addWidget(m_caseListView);

    auto *detailColumn = new QWidget(content);
    auto *detailColumnLayout = new QVBoxLayout(detailColumn);
    detailColumnLayout->setContentsMargins(0, 0, 0, 0);
    detailColumnLayout->setSpacing(0);
    m_caseDetailView = new CaseDetailView(detailColumn);
    detailColumnLayout->addWidget(m_caseDetailView, 1);

    body->addWidget(caseColumn, 1);
    body->addWidget(detailColumn, 2);

    contentLayout->addWidget(header);
    contentLayout->addLayout(body, 1);

    rootLayout->addWidget(sidebar);
    rootLayout->addWidget(content, 1);

    workspace->setStyleSheet(R"(
        QWidget {
            background: #f4f1ea;
            color: #243042;
            font-size: 14px;
        }
        QFrame#sidebar {
            background: #1f2933;
            color: #f9f5ee;
        }
        QLabel#brandLabel {
            color: #f5c28b;
            font-size: 22px;
            font-weight: 700;
            letter-spacing: 1px;
        }
        QPushButton {
            background: #f7efe4;
            border: 1px solid #e6d4bc;
            border-radius: 10px;
            padding: 10px 12px;
            text-align: left;
            font-weight: 600;
        }
        QFrame#sidebar QPushButton {
            background: #293746;
            border: 1px solid #344454;
            color: #f7efe4;
        }
        QFrame#sidebar QPushButton:disabled {
            background: #c97b3d;
            border-color: #c97b3d;
            color: #fff9f2;
        }
        QFrame#headerCard, QFrame#panelCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
        }
        QLabel#pageTitle {
            font-size: 28px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#subtitleLabel {
            color: #607080;
        }
        QLabel#statusChip {
            background: #f4e3cf;
            color: #9c5d2d;
            border-radius: 12px;
            padding: 8px 12px;
            font-weight: 700;
        }
    )");

    if (m_caseListView && m_caseDetailView) {
        connect(m_caseListView, &CaseListView::caseSelected, this, [this](const QString &) {
            syncActiveCaseWorkspace();
        });
        connect(m_caseDetailView, &CaseDetailView::caseDuplicated, this, [this](const QString &newCaseId) {
            if (m_caseListView) {
                m_caseListView->reloadCases(newCaseId, false);
            }
            syncActiveCaseWorkspace();
            statusBar()->showMessage("Byla vytvorena nova pracovni kopie zakazky.", 5000);
        });
        connect(m_caseDetailView, &CaseDetailView::newVariantRequested, this, [this](const QString &caseId) {
            statusBar()->showMessage(
                QString("Nova varianta pro case %1 bude napojena v dalsim kroku.").arg(caseId),
                5000);
        });
        connect(m_caseDetailView, &CaseDetailView::caseSent, this, [this](const QString &caseId) {
            if (m_caseListView) {
                m_caseListView->reloadCases(QString(), false);
            }
            syncActiveCaseWorkspace();
            statusBar()->showMessage(
                QString("Zakazka %1 byla oznacena jako odeslana a presunuta do historie.").arg(caseId),
                5000);
        });
        connect(m_caseListView, &CaseListView::optionRequested, this, [this](const QString &optionKey) {
            QString optionLabel = optionKey;
            if (optionKey == "subject") {
                optionLabel = "Predmet zakazky";
            } else if (optionKey == "material_cost") {
                optionLabel = "Cena materialu";
            } else if (optionKey == "labor_cost") {
                optionLabel = "Cena prace";
            } else if (optionKey == "materials") {
                optionLabel = "Materialy";
            } else if (optionKey == "amortization") {
                optionLabel = "Amortizace";
            } else if (optionKey == "margin") {
                optionLabel = "Marze";
            } else if (optionKey == "material_suppliers") {
                optionLabel = "Dodavatele materialu";
            }
            statusBar()->showMessage(
                QString("Sekce \"%1\" bude napojena jako dalsi krok.").arg(optionLabel),
                4000);
        });

        syncActiveCaseWorkspace();
    }

    connect(workCasesButton, &QPushButton::clicked, this, [this]() {
        statusBar()->showMessage("Rozpracovane zakazky jsou dostupne v levem pracovnim panelu.", 4000);
    });
    connect(historyButton, &QPushButton::clicked, this, [this]() {
        statusBar()->showMessage("Historie zakazek bude napojena jako samostatny pohled v dalsim kroku.", 5000);
    });
    connect(loginButton, &QPushButton::clicked, this, [this]() {
        if (m_stack) {
            m_stack->setCurrentIndex(0);
            switchToLoginMode();
        }
    });

    return workspace;
}

void MainWindow::switchToLoginMode()
{
    showNormal();
    setMinimumSize(900, 420);
    setMaximumSize(900, 420);
    resize(900, 420);
}

void MainWindow::switchToWorkspaceMode()
{
    setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX);
    setMinimumSize(1280, 820);
    resize(1440, 900);
}

void MainWindow::syncActiveCaseWorkspace()
{
    if (!m_caseListView || !m_caseDetailView) {
        return;
    }

    const auto activeCaseId = m_caseListView->currentCaseId();
    if (activeCaseId.isEmpty()) {
        m_caseDetailView->clearCase();
        updateWorkspaceHeader();
        return;
    }

    m_caseDetailView->setCase(activeCaseId);
    updateWorkspaceHeader();
}

void MainWindow::updateWorkspaceHeader()
{
    if (!m_workspaceTitleLabel || !m_workspaceSubtitleLabel || !m_caseListView) {
        return;
    }

    const auto currentTitle = m_caseListView->currentCaseTitle();
    if (currentTitle.isEmpty()) {
        m_workspaceTitleLabel->setText("Zatim neni aktivni zakazka");
        m_workspaceSubtitleLabel->setText(
            "Vyber rozpracovanou zakazku vlevo. Vsechny dulezite kroky budeme drzet v jedne aktualni karte.");
        return;
    }

    m_workspaceTitleLabel->setText(currentTitle);
    if (m_caseListView->currentCaseIsReferenceDataset()) {
        m_workspaceSubtitleLabel->setText(
            "Toto je referencni testovaci zakazka z datasetu. Je vhodna pro overeni analyzy, navrhu a vyberu fotek.");
        return;
    }

    m_workspaceSubtitleLabel->setText(
        "Toto je hlavni pracovni karta aktualni zakazky. Moznosti mas vlevo, tady probiha samotna prace na detailu.");
}
