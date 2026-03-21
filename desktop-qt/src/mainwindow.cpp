#include "mainwindow.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QStackedWidget>
#include <QStatusBar>
#include <QStyle>
#include <QVBoxLayout>

#include "services/apiservice.h"
#include "views/casebrowserview.h"
#include "views/casedetailview.h"
#include "views/caselistview.h"
#include "views/loginview.h"
#include "views/newcaseview.h"

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
{
    setWindowTitle("FotoNabidka Desktop");

    m_stack = new QStackedWidget(this);
    m_loginView = new LoginView(this);
    m_stack->addWidget(m_loginView);
    m_stack->addWidget(createWorkspaceShell());
    m_stack->setCurrentIndex(0);

    setCentralWidget(m_stack);
    switchToLoginMode();

    connect(m_loginView, &LoginView::loginRequested, this, &MainWindow::handleLoginRequested);
}

void MainWindow::handleLoginRequested(const QString &email, const QString &password)
{
    if (!m_loginView) {
        return;
    }

    m_loginView->clearError();
    m_loginView->setLoading(true);

    ApiService api;
    QString errorMessage;
    const auto result = api.login(email, password, &errorMessage);

    m_loginView->setLoading(false);

    if (result.accessToken.isEmpty()) {
        m_loginView->showError(errorMessage.isEmpty() ? "Prihlaseni se nezdarilo." : errorMessage);
        return;
    }

    m_session.setTokens(result.accessToken, result.refreshToken);
    m_session.saveToSettings();
    ApiService::setGlobalToken(result.accessToken);

    m_stack->setCurrentIndex(1);
    switchToWorkspaceMode();

    if (m_caseListView) {
        m_caseListView->reloadCases(QString(), false);  // load list without auto-selecting
    }
    showWelcomeView();
    statusBar()->showMessage(
        QString("Prihlasen jako %1").arg(result.fullName.isEmpty() ? result.email : result.fullName),
        5000);
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

    m_sidebarProjectButton = new QPushButton(QString::fromUtf8("Aktu\u00e1ln\u00ed projekt"), sidebar);
    m_sidebarProjectButton->hide();  // shown only when a case is open
    m_sidebarServerCasesButton = new QPushButton(QString::fromUtf8("Zak\u00e1zky ze serveru"), sidebar);
    m_sidebarWorkCasesButton = new QPushButton(QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky"), sidebar);
    m_sidebarHistoryButton = new QPushButton(QString::fromUtf8("Historie zak\u00e1zek"), sidebar);
    m_sidebarNewCaseButton = new QPushButton(
        QString::fromUtf8("Nov\u00e1 zak\u00e1zka z PC"), sidebar);
    auto *loginButton = new QPushButton("Login view", sidebar);
    sidebarLayout->addWidget(m_sidebarProjectButton);
    sidebarLayout->addWidget(m_sidebarServerCasesButton);
    sidebarLayout->addWidget(m_sidebarWorkCasesButton);
    sidebarLayout->addWidget(m_sidebarHistoryButton);
    sidebarLayout->addWidget(m_sidebarNewCaseButton);
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

    m_caseColumn = new QFrame(content);
    auto *caseColumn = m_caseColumn;
    caseColumn->setObjectName("panelCard");
    auto *caseColumnLayout = new QVBoxLayout(caseColumn);
    caseColumnLayout->setContentsMargins(0, 0, 0, 0);
    m_caseListView = new CaseListView(caseColumn);
    caseColumnLayout->addWidget(m_caseListView);

    auto *detailColumn = new QWidget(content);
    auto *detailColumnLayout = new QVBoxLayout(detailColumn);
    detailColumnLayout->setContentsMargins(0, 0, 0, 0);
    detailColumnLayout->setSpacing(0);
    m_detailStack = new QStackedWidget(detailColumn);
    m_caseDetailView = new CaseDetailView(m_detailStack);
    m_newCaseView = new NewCaseView(m_detailStack);
    m_caseBrowserView = new CaseBrowserView(m_detailStack);
    // Welcome screen (shown on startup before any case is selected)
    m_welcomeView = new QWidget(m_detailStack);
    auto *welcomeLayout = new QVBoxLayout(m_welcomeView);
    welcomeLayout->setContentsMargins(32, 32, 32, 32);
    welcomeLayout->setSpacing(20);
    welcomeLayout->addStretch();

    auto makeWelcomeCard = [](QWidget *parent, const QString &title, const QString &hint) -> QFrame * {
        auto *card = new QFrame(parent);
        card->setObjectName("welcomeCard");
        auto *cardLayout = new QVBoxLayout(card);
        cardLayout->setContentsMargins(24, 20, 24, 20);
        cardLayout->setSpacing(8);
        auto *titleLabel = new QLabel(title, card);
        titleLabel->setObjectName("welcomeCardTitle");
        auto *hintLabel = new QLabel(hint, card);
        hintLabel->setObjectName("welcomeCardHint");
        hintLabel->setWordWrap(true);
        cardLayout->addWidget(titleLabel);
        cardLayout->addWidget(hintLabel);
        return card;
    };

    auto *openServerCard = makeWelcomeCard(m_welcomeView,
        QString::fromUtf8("Otev\u0159\u00edt zak\u00e1zky ze serveru"),
        QString::fromUtf8("Na\u010d\u00edst aktu\u00e1ln\u00ed seznam zak\u00e1zek a aktualizovat frontu."));
    auto *openServerButton = new QPushButton(
        QString::fromUtf8("Na\u010d\u00edst zak\u00e1zky"), openServerCard);
    openServerButton->setFixedWidth(160);
    static_cast<QVBoxLayout*>(openServerCard->layout())->addWidget(openServerButton);

    auto *pickCard = makeWelcomeCard(m_welcomeView,
        QString::fromUtf8("Zvolte si zak\u00e1zku z lev\u00e9ho side baru"),
        QString::fromUtf8("Klikn\u011bte na Projekt nebo Rozpracovan\u00e9 zak\u00e1zky \u2014 vyberte zak\u00e1zku z p\u0159ehledu a za\u010dn\u011bte pracovat."));

    welcomeLayout->addWidget(openServerCard);
    welcomeLayout->addWidget(pickCard);
    welcomeLayout->addStretch();

    m_welcomeView->setStyleSheet(R"(
        QFrame#welcomeCard {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 16px;
        }
        QLabel#welcomeCardTitle {
            font-size: 17px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#welcomeCardHint {
            color: #607080;
            font-size: 13px;
        }
    )");

    m_detailStack->addWidget(m_caseDetailView);   // index 0
    m_detailStack->addWidget(m_newCaseView);       // index 1
    m_detailStack->addWidget(m_caseBrowserView);   // index 2
    m_detailStack->addWidget(m_welcomeView);       // index 3
    m_detailStack->setCurrentIndex(3);
    detailColumnLayout->addWidget(m_detailStack, 1);

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
        QPushButton#sidebarButtonActive {
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
        connect(m_caseListView, &CaseListView::sessionExpired, this, &MainWindow::handleSessionExpired);
        connect(m_caseDetailView, &CaseDetailView::sessionExpired, this, &MainWindow::handleSessionExpired);
        connect(m_newCaseView, &NewCaseView::cancelled, this, [this]() {
            showCaseDetailView();
        });
        connect(m_newCaseView, &NewCaseView::sessionExpired, this, &MainWindow::handleSessionExpired);
        connect(m_newCaseView, &NewCaseView::caseCreated, this, [this](const QString &caseId) {
            showCaseDetailView();
            if (m_caseListView) {
                m_caseListView->reloadCases(caseId, false);
            }
            syncActiveCaseWorkspace();
            statusBar()->showMessage(
                QString::fromUtf8("Nov\u00e1 zak\u00e1zka vytvo\u0159ena a anal\u00fdza spu\u0161t\u011bna."),
                5000);
        });

        connect(m_caseListView, &CaseListView::optionRequested, this, [this](const QString &optionKey) {
            if (optionKey == "upload_photos") {
                showCaseDetailView();
                if (m_caseDetailView) {
                    m_caseDetailView->switchToPhotosTab();
                }
                return;
            }
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

        connect(openServerButton, &QPushButton::clicked, this, [this]() {
            if (m_caseListView) m_caseListView->reloadCases(QString(), true);
        });

        // On startup show welcome instead of empty case detail
        showWelcomeView();
    }

    connect(m_sidebarProjectButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        showCaseDetailView();
        setSidebarActiveSection(m_sidebarProjectButton);
    });
    connect(m_sidebarServerCasesButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        if (m_caseListView) m_caseListView->reloadCases(QString(), false);
        showWelcomeView();
        setSidebarActiveSection(m_sidebarServerCasesButton);
    });
    connect(m_sidebarWorkCasesButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        if (m_caseColumn) m_caseColumn->show();
        if (m_caseBrowserView) m_caseBrowserView->loadCases(CaseBrowserView::Mode::WorkCases);
        if (m_detailStack) m_detailStack->setCurrentIndex(2);
        setSidebarActiveSection(m_sidebarWorkCasesButton);
    });
    connect(m_sidebarHistoryButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        if (m_caseColumn) m_caseColumn->show();
        if (m_caseBrowserView) m_caseBrowserView->loadCases(CaseBrowserView::Mode::HistoryCases);
        if (m_detailStack) m_detailStack->setCurrentIndex(2);
        setSidebarActiveSection(m_sidebarHistoryButton);
    });
    connect(m_sidebarNewCaseButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        showNewCaseView();
        setSidebarActiveSection(m_sidebarNewCaseButton);
    });
    connect(m_caseBrowserView, &CaseBrowserView::caseOpenRequested, this,
        [this](const QString &caseId, bool readOnly) {
            if (m_caseListView) m_caseListView->setCurrentCaseId(caseId, false);
            showCaseDetailView();
            if (m_caseDetailView) {
                m_caseDetailView->setCase(caseId);
                m_caseDetailView->setReadOnly(readOnly);
                if (m_caseListView) m_caseListView->updateForCaseSource(m_caseDetailView->caseSource());
            }
            updateWorkspaceHeader();
            setSidebarActiveSection(m_sidebarProjectButton);
        });
    connect(m_caseBrowserView, &CaseBrowserView::sessionExpired, this, &MainWindow::handleSessionExpired);
    connect(loginButton, &QPushButton::clicked, this, [this]() {
        m_session.clear();
        ApiService::clearGlobalToken();
        if (m_loginView) {
            m_loginView->clearError();
        }
        if (m_stack) {
            m_stack->setCurrentIndex(0);
            switchToLoginMode();
        }
    });

    return workspace;
}

void MainWindow::handleSessionExpired()
{
    m_session.clear();
    ApiService::clearSessionExpired();
    if (m_loginView) {
        m_loginView->clearError();
        m_loginView->showError("Relace vyprsela. Prihlas se prosim znovu.");
    }
    if (m_stack) {
        m_stack->setCurrentIndex(0);
        switchToLoginMode();
    }
}

void MainWindow::showNewCaseView()
{
    if (m_caseColumn) m_caseColumn->show();
    if (m_newCaseView) m_newCaseView->reset();
    if (m_detailStack) m_detailStack->setCurrentIndex(1);
    if (m_workspaceTitleLabel)
        m_workspaceTitleLabel->setText(QString::fromUtf8("Nov\u00e1 zak\u00e1zka z PC"));
    if (m_workspaceSubtitleLabel)
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Vytvo\u0159te novou zak\u00e1zku nahran\u00edm fotografii z po\u010d\u00eda\u010de."));
    setSidebarActiveSection(m_sidebarNewCaseButton);
}

void MainWindow::showWelcomeView()
{
    if (m_sidebarProjectButton) m_sidebarProjectButton->hide();
    if (m_caseColumn) m_caseColumn->hide();
    if (m_detailStack) m_detailStack->setCurrentIndex(3);
    if (m_workspaceTitleLabel)
        m_workspaceTitleLabel->setText(QString::fromUtf8("V\u00edtejte"));
    if (m_workspaceSubtitleLabel)
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Vyberte zak\u00e1zku nebo na\u010dt\u011bte frontu ze serveru."));
    setSidebarActiveSection(nullptr);
}

void MainWindow::showCaseDetailView()
{
    if (m_sidebarProjectButton) m_sidebarProjectButton->show();
    if (m_caseColumn) m_caseColumn->show();
    if (m_detailStack) m_detailStack->setCurrentIndex(0);
    updateWorkspaceHeader();
    setSidebarActiveSection(m_sidebarProjectButton);
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
        m_caseListView->updateForCaseSource(QString());
        updateWorkspaceHeader();
        return;
    }

    m_caseDetailView->setCase(activeCaseId);
    m_caseDetailView->setReadOnly(false);
    m_caseListView->updateForCaseSource(m_caseDetailView->caseSource());
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

void MainWindow::setSidebarActiveSection(QPushButton *activeButton)
{
    const QString activeStyle =
        "background: #c97b3d; border-color: #c97b3d; color: #fff9f2;";
    const QList<QPushButton *> buttons = {
        m_sidebarProjectButton, m_sidebarServerCasesButton,
        m_sidebarWorkCasesButton, m_sidebarHistoryButton, m_sidebarNewCaseButton
    };
    for (auto *btn : buttons) {
        if (!btn) continue;
        btn->setStyleSheet(btn == activeButton ? activeStyle : QString());
    }
}

bool MainWindow::confirmNavigateAway()
{
    if (!m_caseDetailView || !m_caseDetailView->hasUnsavedChanges()) return true;
    if (m_detailStack && m_detailStack->currentIndex() != 0) return true;

    const auto answer = QMessageBox::question(
        this,
        QString::fromUtf8("Neulo\u017een\u00e9 zm\u011bny"),
        QString::fromUtf8("M\u00e1te neulo\u017een\u00e9 zm\u011bny v aktu\u00e1ln\u00ed zak\u00e1zce. Chcete odej\u00edt bez ulo\u017een\u00ed?"),
        QMessageBox::Yes | QMessageBox::No,
        QMessageBox::No);
    return answer == QMessageBox::Yes;
}
