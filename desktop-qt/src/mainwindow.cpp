#include "mainwindow.h"

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QMessageBox>
#include <QPushButton>
#include <QDialog>
#include <QScrollArea>
#include <QSettings>
#include <QStackedWidget>
#include <QStatusBar>
#include <QStyle>
#include <QVBoxLayout>
#include <QTimer>
#include <QWhatsThis>

#include "dto/loginresultdto.h"
#include "services/apiservice.h"
#include "views/adminpanelview.h"
#include "views/casebrowserview.h"
#include "views/casedetailview.h"
#include "views/caselistview.h"
#include "views/loginview.h"
#include "views/newcaseview.h"
#include "views/serversetupdialog.h"

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , m_apiService(new ApiService(m_session, this))
{
    setWindowTitle("NOVU Builder");

    // Load server URL from settings; prompt setup on first launch
    QSettings settings("NOVU", "NovuBuilder");
    const QString savedUrl = settings.value("server/url").toString();
    if (savedUrl.isEmpty()) {
        openServerSetupDialog(true);
    } else {
        ApiService::setGlobalBaseUrl(savedUrl);
        m_session.refreshRealtimeConnection();
    }

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

    m_apiService->login(email, password,
        [this](LoginResultDto result) {
            if (!m_loginView) return;
            m_loginView->setLoading(false);

            m_session.setTokens(result.accessToken, result.refreshToken);
            m_session.saveToSettings();

            const bool isSuperAdmin = result.isSuperAdmin
                || result.role == QLatin1String("superadmin");

            if (m_serverButton) {
                const bool isAdmin = isSuperAdmin
                    || result.role == QLatin1String("company-admin");
                m_serverButton->setVisible(isAdmin);
            }
            if (m_sidebarAdminButton) {
                m_sidebarAdminButton->setVisible(isSuperAdmin);
            }

            m_stack->setCurrentIndex(1);
            switchToWorkspaceMode();

            if (m_caseListView) {
                m_caseListView->reloadCases(QString(), false);
            }
            showWelcomeView();
            statusBar()->showMessage(
                QString("Prihlasen jako %1").arg(result.fullName.isEmpty() ? result.email : result.fullName),
                5000);
        },
        [this](const QString &errorMessage) {
            if (!m_loginView) return;
            m_loginView->setLoading(false);
            m_loginView->showError(errorMessage.isEmpty() ? "Prihlaseni se nezdarilo." : errorMessage);
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

    m_sidebarServerCasesButton = new QPushButton(QString::fromUtf8("Zak\u00e1zky ze serveru"), sidebar);
    m_sidebarServerCasesButton->setWhatsThis(QString::fromUtf8("Na\u010dte aktu\u00e1ln\u00ed frontu zak\u00e1zek ze serveru. Zobraz\u00ed v\u0161echny zak\u00e1zky p\u0159i\u0159azen\u00e9 va\u0161\u00ed firm\u011b."));
    m_sidebarWorkCasesButton = new QPushButton(QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky"), sidebar);
    m_sidebarWorkCasesButton->setWhatsThis(QString::fromUtf8("Zobraz\u00ed p\u0159ehled v\u0161ech zak\u00e1zek, na kter\u00fdch se pracuje (stav: rozpracov\u00e1no, analyzov\u00e1no, zpracov\u00e1v\u00e1 se)."));
    m_sidebarHistoryButton = new QPushButton(QString::fromUtf8("Historie zak\u00e1zek"), sidebar);
    m_sidebarHistoryButton->setWhatsThis(QString::fromUtf8("Zobraz\u00ed dokon\u010den\u00e9 a odeslan\u00e9 zak\u00e1zky. Tyto zak\u00e1zky jsou jen pro \u010dten\u00ed."));
    m_sidebarNewCaseButton = new QPushButton(
        QString::fromUtf8("Nov\u00e1 zak\u00e1zka z PC"), sidebar);
    m_sidebarNewCaseButton->setWhatsThis(QString::fromUtf8("Vytvo\u0159\u00ed novou zak\u00e1zku p\u0159\u00edmo z po\u010d\u00edta\u010de \u2014 bez mobiln\u00ed aplikace. Vhodn\u00e9 pro archivn\u00ed nebo testovac\u00ed zak\u00e1zky."));
    auto *loginButton = new QPushButton("Login view", sidebar);
    loginButton->setWhatsThis(QString::fromUtf8("Odhl\u00e1s\u00ed aktu\u00e1ln\u00edho u\u017eivatele a vr\u00e1t\u00ed se na p\u0159ihla\u0161ovac\u00ed obrazovku."));
    m_sidebarAdminButton = new QPushButton(QString::fromUtf8("\u2699 Admin"), sidebar);
    m_sidebarAdminButton->setWhatsThis(QString::fromUtf8("Otev\u0159e admin panel \u2014 spr\u00e1va u\u017eivatel\u016f, p\u0159ehled jobs a logy serveru. Pouze pro superadmina."));
    m_sidebarAdminButton->setVisible(false);

    sidebarLayout->addWidget(m_sidebarServerCasesButton);
    sidebarLayout->addWidget(m_sidebarWorkCasesButton);
    sidebarLayout->addWidget(m_sidebarHistoryButton);
    sidebarLayout->addWidget(m_sidebarNewCaseButton);
    sidebarLayout->addStretch();
    sidebarLayout->addWidget(m_sidebarAdminButton);
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

    auto *whatsThisButton = new QPushButton("?", header);
    whatsThisButton->setObjectName("headerIconButton");
    whatsThisButton->setFixedSize(32, 32);
    whatsThisButton->setToolTip(QString::fromUtf8("Co je tohle? — klikni a pak na libovolný prvek"));
    whatsThisButton->setWhatsThis(QString::fromUtf8("Aktivuje re\u017eim n\u00e1pov\u011bdy. Kurzor se zm\u011bn\u00ed na otazn\u00edk \u2014 klikni na libovoln\u00fd prvek pro zobrazen\u00ed popisu."));

    auto *helpButton = new QPushButton(QString::fromUtf8("N\u00e1pov\u011bda"), header);
    helpButton->setObjectName("headerIconButton");
    helpButton->setFixedHeight(32);
    helpButton->setWhatsThis(QString::fromUtf8("Otev\u0159e okno s p\u0159ehledem cel\u00e9ho workflow a popisem v\u0161ech \u010d\u00e1st\u00ed aplikace."));

    auto *troubleshootButton = new QPushButton(QString::fromUtf8("\u0158e\u0161en\u00ed pot\u00ed\u017e\u00ed"), header);
    troubleshootButton->setObjectName("headerIconButton");
    troubleshootButton->setFixedHeight(32);
    troubleshootButton->setWhatsThis(QString::fromUtf8("Otev\u0159e pr\u016fvodce \u0159e\u0161en\u00edm b\u011b\u017en\u00fdch pot\u00ed\u017e\u00ed \u2014 backend nedostupn\u00fd, anal\u00fdza se nespust\u00ed, export nefunguje apod."));

    m_serverButton = new QPushButton(QString::fromUtf8("\u2699 Server"), header);
    m_serverButton->setObjectName("headerIconButton");
    m_serverButton->setFixedHeight(32);
    m_serverButton->setToolTip(QString::fromUtf8("Zm\u011bnit adresu serveru"));
    m_serverButton->setWhatsThis(QString::fromUtf8("Otev\u0159e dialog pro nastaven\u00ed adresy NOVU serveru Va\u0161\u00ed firmy."));
    auto *serverSettingsButton = m_serverButton;

    m_workspaceTitleLabel->setWhatsThis(QString::fromUtf8("N\u00e1zev aktu\u00e1ln\u011b otev\u0159en\u00e9 zak\u00e1zky nebo sekce."));
    m_workspaceSubtitleLabel->setWhatsThis(QString::fromUtf8("Stru\u010dn\u00fd popis aktu\u00e1ln\u00ed sekce nebo zak\u00e1zky."));
    statusChip->setWhatsThis(QString::fromUtf8("Verze desktop aplikace."));

    auto *headerButtons = new QHBoxLayout();
    headerButtons->setSpacing(6);
    headerButtons->addWidget(whatsThisButton);
    headerButtons->addWidget(helpButton);
    headerButtons->addWidget(troubleshootButton);
    headerButtons->addWidget(serverSettingsButton);

    headerLayout->addLayout(titleColumn, 1);
    headerLayout->addWidget(statusChip, 0, Qt::AlignTop);
    headerLayout->addLayout(headerButtons, 0);

    auto *body = new QHBoxLayout();
    body->setSpacing(18);

    m_caseColumn = new QFrame(content);
    auto *caseColumn = m_caseColumn;
    caseColumn->setObjectName("panelCard");
    auto *caseColumnLayout = new QVBoxLayout(caseColumn);
    caseColumnLayout->setContentsMargins(0, 0, 0, 0);
    m_caseListView = new CaseListView(m_session, caseColumn);
    caseColumnLayout->addWidget(m_caseListView);

    auto *detailColumn = new QWidget(content);
    auto *detailColumnLayout = new QVBoxLayout(detailColumn);
    detailColumnLayout->setContentsMargins(0, 0, 0, 0);
    detailColumnLayout->setSpacing(0);
    m_detailStack = new QStackedWidget(detailColumn);
    m_caseDetailView = new CaseDetailView(m_session, m_detailStack);
    m_newCaseView = new NewCaseView(m_session, m_detailStack);
    m_caseBrowserView = new CaseBrowserView(m_session, m_detailStack);
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
    openServerButton->setWhatsThis(QString::fromUtf8("Na\u010dte frontu zak\u00e1zek ze serveru a aktualizuje seznam Rozpracovan\u00fdch zak\u00e1zek."));
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

    m_adminPanelView = new AdminPanelView(m_session, m_detailStack);
    connect(m_adminPanelView, &AdminPanelView::impersonationStarted,
            this, &MainWindow::startImpersonation);

    m_detailStack->addWidget(m_caseDetailView);   // index 0
    m_detailStack->addWidget(m_newCaseView);       // index 1
    m_detailStack->addWidget(m_caseBrowserView);   // index 2
    m_detailStack->addWidget(m_welcomeView);       // index 3
    m_detailStack->addWidget(m_adminPanelView);    // index 4
    m_detailStack->setCurrentIndex(3);
    detailColumnLayout->addWidget(m_detailStack, 1);

    body->addWidget(caseColumn, 1);
    body->addWidget(detailColumn, 2);

    // Impersonation banner (hidden by default, shown when impersonating)
    m_impersonationBanner = new QFrame(content);
    m_impersonationBanner->setObjectName("impersonationBanner");
    auto *bannerLayout = new QHBoxLayout(m_impersonationBanner);
    bannerLayout->setContentsMargins(16, 8, 16, 8);
    bannerLayout->setSpacing(12);
    m_impersonationLabel = new QLabel(m_impersonationBanner);
    m_impersonationLabel->setObjectName("impersonationLabel");
    m_stopImpersonationBtn = new QPushButton(QString::fromUtf8("Ukon\u010dit impersonaci"), m_impersonationBanner);
    m_stopImpersonationBtn->setObjectName("stopImpersonationBtn");
    m_stopImpersonationBtn->setFixedHeight(28);
    bannerLayout->addWidget(m_impersonationLabel, 1);
    bannerLayout->addWidget(m_stopImpersonationBtn);
    m_impersonationBanner->setVisible(false);
    m_impersonationBanner->setStyleSheet(R"(
        QFrame#impersonationBanner {
            background: #fff3cd;
            border: 1px solid #f0c040;
            border-radius: 8px;
        }
        QLabel#impersonationLabel {
            color: #7b5a00;
            font-weight: 600;
            font-size: 13px;
        }
        QPushButton#stopImpersonationBtn {
            background: #e0a800;
            border: 1px solid #c89500;
            border-radius: 6px;
            color: #fff;
            font-weight: 700;
            padding: 4px 12px;
        }
        QPushButton#stopImpersonationBtn:hover {
            background: #c89500;
        }
    )");
    connect(m_stopImpersonationBtn, &QPushButton::clicked, this, &MainWindow::stopImpersonation);

    contentLayout->addWidget(m_impersonationBanner);
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
        QPushButton#headerIconButton {
            background: #f0e8da;
            border: 1px solid #d9c9b0;
            border-radius: 8px;
            color: #6b4f2e;
            font-weight: 700;
            padding: 4px 10px;
        }
        QPushButton#headerIconButton:hover {
            background: #e8d9c4;
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
        connect(m_adminPanelView, &AdminPanelView::sessionExpired, this, &MainWindow::handleSessionExpired);
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
            if (optionKey == QLatin1String("upload_photos")) {
                showCaseDetailView();
                if (m_caseDetailView) m_caseDetailView->switchToPhotosTab();
                return;
            }
            if (optionKey == QLatin1String("save")) {
                if (m_caseDetailView) m_caseDetailView->triggerSave();
                return;
            }
            showCaseDetailView();
            if (m_caseDetailView) m_caseDetailView->navigateToField(optionKey);
        });

        connect(openServerButton, &QPushButton::clicked, this, [this]() {
            m_caseListSection = QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky");
            if (m_caseListView) m_caseListView->reloadCases(QString(), false);
            if (m_caseColumn) m_caseColumn->hide();
            if (m_caseBrowserView) m_caseBrowserView->loadCases(CaseBrowserView::Mode::WorkCases);
            if (m_detailStack) m_detailStack->setCurrentIndex(2);
            if (m_workspaceTitleLabel)
                m_workspaceTitleLabel->setText(m_caseListSection);
            if (m_workspaceSubtitleLabel)
                m_workspaceSubtitleLabel->setText(QString::fromUtf8("Zak\u00e1zky, na kter\u00fdch se pracuje."));
            setSidebarActiveSection(m_sidebarWorkCasesButton);
        });

        // On startup show welcome instead of empty case detail
        showWelcomeView();
    }

    connect(m_sidebarServerCasesButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        if (m_caseListView) m_caseListView->reloadCases(QString(), false);
        showWelcomeView();
        setSidebarActiveSection(m_sidebarServerCasesButton);
    });
    connect(m_sidebarWorkCasesButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        m_caseListSection = QString::fromUtf8("Rozpracovan\u00e9 zak\u00e1zky");
        if (m_caseColumn) m_caseColumn->hide();
        if (m_caseBrowserView) m_caseBrowserView->loadCases(CaseBrowserView::Mode::WorkCases);
        if (m_detailStack) m_detailStack->setCurrentIndex(2);
        if (m_workspaceTitleLabel)
            m_workspaceTitleLabel->setText(m_caseListSection);
        if (m_workspaceSubtitleLabel)
            m_workspaceSubtitleLabel->setText(QString::fromUtf8("Zak\u00e1zky, na kter\u00fdch se pracuje."));
        setSidebarActiveSection(m_sidebarWorkCasesButton);
    });
    connect(m_sidebarHistoryButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        m_caseListSection = QString::fromUtf8("Historie zak\u00e1zek");
        if (m_caseColumn) m_caseColumn->hide();
        if (m_caseBrowserView) m_caseBrowserView->loadCases(CaseBrowserView::Mode::HistoryCases);
        if (m_detailStack) m_detailStack->setCurrentIndex(2);
        if (m_workspaceTitleLabel)
            m_workspaceTitleLabel->setText(m_caseListSection);
        if (m_workspaceSubtitleLabel)
            m_workspaceSubtitleLabel->setText(QString::fromUtf8("Dokon\u010den\u00e9 a odeslan\u00e9 zak\u00e1zky."));
        setSidebarActiveSection(m_sidebarHistoryButton);
    });
    connect(m_sidebarNewCaseButton, &QPushButton::clicked, this, [this]() {
        if (!confirmNavigateAway()) return;
        showNewCaseView();
        setSidebarActiveSection(m_sidebarNewCaseButton);
    });
    connect(m_sidebarAdminButton, &QPushButton::clicked, this, [this]() {
        showAdminPanelView();
        setSidebarActiveSection(m_sidebarAdminButton);
    });

    // WhatsThis mode
    connect(whatsThisButton, &QPushButton::clicked, this, []() {
        QTimer::singleShot(0, []() { QWhatsThis::enterWhatsThisMode(); });
    });

    // Help dialog
    connect(helpButton, &QPushButton::clicked, this, [this]() {
        auto *dlg = new QDialog(this);
        dlg->setWindowTitle(QString::fromUtf8("N\u00e1pov\u011bda \u2014 FotoNab\u00eddka Desktop"));
        dlg->setMinimumSize(520, 480);
        auto *dlgLayout = new QVBoxLayout(dlg);
        dlgLayout->setContentsMargins(24, 20, 24, 20);
        dlgLayout->setSpacing(12);

        auto *scroll = new QScrollArea(dlg);
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        auto *inner = new QWidget();
        auto *innerLayout = new QVBoxLayout(inner);
        innerLayout->setSpacing(16);

        const auto addSection = [&](const QString &title, const QString &text) {
            auto *t = new QLabel("<b>" + title + "</b>", inner);
            t->setStyleSheet("font-size: 14px; color: #1f2933;");
            auto *b = new QLabel(text, inner);
            b->setWordWrap(true);
            b->setStyleSheet("color: #314252; font-size: 13px;");
            innerLayout->addWidget(t);
            innerLayout->addWidget(b);
        };

        addSection(QString::fromUtf8("Jak to funguje"),
            QString::fromUtf8(
                "Technik v ter\u00e9nu nafot\u00ed poškozen\u00e9 m\u00edsto mobiln\u00ed aplikac\u00ed. "
                "Server automaticky analyzuje fotky pomoc\u00ed AI \u2014 zjist\u00ed plochu, "
                "navrhne materi\u00e1ly a postup pr\u00e1ce. "
                "Dispečer na desktopu zkontroluje v\u00fdsledky, uprav\u00ed ceny a odeš\u0435le PDF nab\u00eddku z\u00e1kazn\u00edkovi."));

        addSection(QString::fromUtf8("Lev\u00fd panel \u2014 sidebar"),
            QString::fromUtf8(
                "\u2022 <b>Zak\u00e1zky ze serveru</b> \u2014 vr\u00e1t\u00ed se na \u00favodni obrazovku a na\u010dte frontu zak\u00e1zek.\n"
                "\u2022 <b>Aktu\u00e1ln\u00ed projekt</b> \u2014 zobraz\u00ed detail pr\u00e1v\u011b otev\u0159en\u00e9 zak\u00e1zky.\n"
                "\u2022 <b>Rozpracovan\u00e9 zak\u00e1zky</b> \u2014 seznam v\u0161ech aktivn\u00edch zak\u00e1zek.\n"
                "\u2022 <b>Historie zak\u00e1zek</b> \u2014 dokon\u010den\u00e9 a odeslan\u00e9 zak\u00e1zky.\n"
                "\u2022 <b>Nov\u00e1 zak\u00e1zka z PC</b> \u2014 vytvo\u0159\u00ed novou zak\u00e1zku p\u0159\u00edmo z po\u010d\u00eda\u010de (desktop workflow)."));

        addSection(QString::fromUtf8("Panel Mo\u017enosti"),
            QString::fromUtf8(
                "Zobraz\u00ed se po v\u00fdb\u011bru zak\u00e1zky. U mobiln\u00edch zak\u00e1zek klikni na "
                "<b>Editovat zak\u00e1zku \u25bc</b> pro rozbal\u00e1n\u00ed pol\u00ed (p\u0159edm\u011bt, ceny, materi\u00e1ly...). "
                "U desktop zak\u00e1zek jsou pol\u00ed vid\u011bln\u00e1 p\u0159\u00edmo."));

        addSection(QString::fromUtf8("Z\u00e1lo\u017eky zak\u00e1zky"),
            QString::fromUtf8(
                "\u2022 <b>P\u0159ehled</b> \u2014 souhrn AI anal\u00fdzy, cenov\u00fd souhrn, hlavn\u00ed fotka, workflow stav.\n"
                "\u2022 <b>Fotky</b> \u2014 spr\u00e1va fotek, nastaven\u00ed prim\u00e1rn\u00ed a referen\u010dn\u00ed fotky pro AI.\n"
                "\u2022 <b>Anal\u00fdza</b> \u2014 v\u00fdsledky AI anal\u00fdzy, \u00faprava plochy a polygonu (jen desktop zak\u00e1zky).\n"
                "\u2022 <b>Nab\u00eddka</b> \u2014 editace nab\u00eddky, pracovn\u00ed polo\u017eky, materi\u00e1ly, fin\u00e1ln\u00ed n\u00e1vrh.\n"
                "\u2022 <b>V\u00fdstup zak\u00e1zky</b> \u2014 export do DOCX/PDF a odesl\u00e1n\u00ed z\u00e1kazn\u00edkovi."));

        addSection(QString::fromUtf8("Tip: Co je tohle?"),
            QString::fromUtf8(
                "Klikni na tla\u010d\u00edtko <b>?</b> v z\u00e1hlav\u00ed \u2014 kurzor se zm\u011bn\u00ed na otazn\u00edk. "
                "Potom klikni na libovoln\u00fd prvek v aplikaci a zobraz\u00ed se bublina s popisem."));

        innerLayout->addStretch();
        scroll->setWidget(inner);
        dlgLayout->addWidget(scroll);

        auto *closeBtn = new QPushButton(QString::fromUtf8("Zav\u0159\u00edt"), dlg);
        connect(closeBtn, &QPushButton::clicked, dlg, &QDialog::accept);
        dlgLayout->addWidget(closeBtn, 0, Qt::AlignRight);

        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->exec();
    });

    // Troubleshooting dialog
    connect(troubleshootButton, &QPushButton::clicked, this, [this]() {
        auto *dlg = new QDialog(this);
        dlg->setWindowTitle(QString::fromUtf8("\u0158e\u0161en\u00ed pot\u00ed\u017e\u00ed \u2014 FotoNab\u00eddka Desktop"));
        dlg->setMinimumSize(540, 500);
        auto *dlgLayout = new QVBoxLayout(dlg);
        dlgLayout->setContentsMargins(24, 20, 24, 20);
        dlgLayout->setSpacing(12);

        auto *scroll = new QScrollArea(dlg);
        scroll->setWidgetResizable(true);
        scroll->setFrameShape(QFrame::NoFrame);
        auto *inner = new QWidget();
        auto *innerLayout = new QVBoxLayout(inner);
        innerLayout->setSpacing(16);

        const auto addIssue = [&](const QString &title, const QString &solution) {
            auto *t = new QLabel(QString::fromUtf8("\u26a0\ufe0f ") + "<b>" + title + "</b>", inner);
            t->setStyleSheet("font-size: 14px; color: #7b3a1e;");
            auto *b = new QLabel(solution, inner);
            b->setWordWrap(true);
            b->setStyleSheet("color: #314252; font-size: 13px;");
            innerLayout->addWidget(t);
            innerLayout->addWidget(b);
        };

        addIssue(
            QString::fromUtf8("Nelze se p\u0159ihl\u00e1sit / server nedostupn\u00fd"),
            QString::fromUtf8(
                "1. Zkontroluj p\u0159ipojen\u00ed k internetu.\n"
                "2. Ov\u011b\u0159 p\u0159ihl\u00e1\u0161ovac\u00ed \u00fadaje (e-mail a heslo) \u2014 heslo je rozli\u0161ov\u00e1no velk\u00fdmi a mal\u00fdmi p\u00edsmeny.\n"
                "3. Pokud pot\u00ed\u017ee p\u0159etrv\u00e1vaj\u00ed, kontaktuj spr\u00e1vce syst\u00e9mu."));

        addIssue(
            QString::fromUtf8("Anal\u00fdza se nespust\u00ed nebo zust\u00e1v\u00e1 ve stavu \u201epending\u201c"),
            QString::fromUtf8(
                "1. Zak\u00e1zka mus\u00ed m\u00edt alespo\u0148 jednu fotku nastavenou jako hlavn\u00ed (primary).\n"
                "2. Zkontroluj z\u00e1lo\u017eku <b>Fotky</b> \u2014 ozna\u010d spr\u00e1vnou fotku p\u0159ep\u00edna\u010dem Primary.\n"
                "3. Klikni na tla\u010d\u00edtko <b>Spustit anal\u00fdzu</b> v z\u00e1lo\u017ece Anal\u00fdza.\n"
                "4. Pokud anal\u00fdza d\u00e9le neodpov\u00edd\u00e1, kontaktuj spr\u00e1vce."));

        addIssue(
            QString::fromUtf8("Fotky se nenahr\u00e1vaj\u00ed nebo chyb\u00ed n\u00e1hled"),
            QString::fromUtf8(
                "1. Ov\u011b\u0159 form\u00e1t soubor\u016f \u2014 podporov\u00e1ny jsou JPG, JPEG, PNG.\n"
                "2. Zkontroluj p\u0159ipojen\u00ed k internetu.\n"
                "3. U Nov\u00e9 zak\u00e1zky z PC: fotky mus\u00ed b\u00fdt vybr\u00e1ny p\u0159ed kliknut\u00edm na <b>Odeslat</b>."));

        addIssue(
            QString::fromUtf8("Export DOCX/PDF nefunguje nebo je tla\u010d\u00edtko ned\u00e1bn\u00e9"),
            QString::fromUtf8(
                "1. Export vy\u017eaduje dokon\u010denou anal\u00fdzu.\n"
                "2. Pro <b>pracovn\u00ed DOCX</b> sta\u010d\u00ed, aby anal\u00fdza prob\u011bhla.\n"
                "3. Pro <b>fin\u00e1ln\u00ed DOCX a PDF</b> mus\u00ed b\u00fdt nejprve vytvo\u0159en fin\u00e1ln\u00ed n\u00e1vrh "
                "(tla\u010d\u00edtko <b>Vytvo\u0159it fin\u00e1ln\u00ed verzi</b> v z\u00e1lo\u017ece Nab\u00eddka)."));

        addIssue(
            QString::fromUtf8("Tla\u010d\u00edtko \u201eOdeslat z\u00e1kazn\u00edkovi\u201c je ned\u00e1bn\u00e9"),
            QString::fromUtf8(
                "Odesl\u00e1n\u00ed vy\u017eaduje vytvo\u0159en\u00fd fin\u00e1ln\u00ed n\u00e1vrh. "
                "Jdi do z\u00e1lo\u017eky <b>Nab\u00eddka</b> a klikni na <b>Vytvo\u0159it fin\u00e1ln\u00ed verzi</b>. "
                "Po vytvo\u0159en\u00ed fin\u00e1ln\u00edho n\u00e1vrhu se tla\u010d\u00edtko Odeslat odem\u010dne."));

        addIssue(
            QString::fromUtf8("Aplikace zobrazuje \u201eRelace vypr\u0161ela\u201c"),
            QString::fromUtf8(
                "Autentiza\u010dn\u00ed token expiroval. Odhla\u0161 se (tla\u010d\u00edtko <b>Login view</b> v sidebarum) "
                "a p\u0159ihla\u0161 se znovu sv\u00fdmi p\u0159ihla\u0161ovac\u00edmi \u00fadaji."));

        innerLayout->addStretch();
        scroll->setWidget(inner);
        dlgLayout->addWidget(scroll);

        auto *closeBtn = new QPushButton(QString::fromUtf8("Zav\u0159\u00edt"), dlg);
        connect(closeBtn, &QPushButton::clicked, dlg, &QDialog::accept);
        dlgLayout->addWidget(closeBtn, 0, Qt::AlignRight);

        dlg->setAttribute(Qt::WA_DeleteOnClose);
        dlg->exec();
    });

    // Server settings button
    connect(serverSettingsButton, &QPushButton::clicked, this, [this]() {
        openServerSetupDialog(false);
    });

    // WhatsThis texts for sidebar buttons
    if (m_sidebarServerCasesButton)
        m_sidebarServerCasesButton->setWhatsThis(QString::fromUtf8("Na\u010dte aktu\u00e1ln\u00ed frontu zak\u00e1zek ze serveru a vr\u00e1t\u00ed se na \u00favodni obrazovku."));
    if (m_sidebarWorkCasesButton)
        m_sidebarWorkCasesButton->setWhatsThis(QString::fromUtf8("Seznam v\u0161ech aktivn\u00edch (rozpracovan\u00fdch) zak\u00e1zek v syst\u00e9mu."));
    if (m_sidebarHistoryButton)
        m_sidebarHistoryButton->setWhatsThis(QString::fromUtf8("Dokon\u010den\u00e9 a odeslan\u00e9 zak\u00e1zky \u2014 pouze pro prohl\u00ed\u017een\u00ed."));
    if (m_sidebarNewCaseButton)
        m_sidebarNewCaseButton->setWhatsThis(QString::fromUtf8("Vytvo\u0159\u00ed novou zak\u00e1zku p\u0159\u00edmo z po\u010d\u00eda\u010de \u2014 ur\u010deno pro desktop workflow s nahr\u00e1n\u00edm fotek z po\u010d\u00eda\u010de."));

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
            // Keep sidebar on the section the case was opened from
            const bool isHistory = (m_caseListSection == QString::fromUtf8("Historie zak\u00e1zek"));
            setSidebarActiveSection(isHistory ? m_sidebarHistoryButton : m_sidebarWorkCasesButton);
        });
    connect(m_caseBrowserView, &CaseBrowserView::sessionExpired, this, &MainWindow::handleSessionExpired);
    connect(loginButton, &QPushButton::clicked, this, [this]() {
        m_session.clear();
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
    if (m_caseColumn) m_caseColumn->hide();
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
    if (m_caseColumn) m_caseColumn->hide();
    if (m_detailStack) m_detailStack->setCurrentIndex(3);
    if (m_workspaceTitleLabel)
        m_workspaceTitleLabel->setText(QString::fromUtf8("V\u00edtejte"));
    if (m_workspaceSubtitleLabel)
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Vyberte zak\u00e1zku nebo na\u010dt\u011bte frontu ze serveru."));
    setSidebarActiveSection(nullptr);
}

void MainWindow::showAdminPanelView()
{
    if (m_caseColumn) m_caseColumn->hide();
    if (m_detailStack) m_detailStack->setCurrentIndex(4);
    if (m_workspaceTitleLabel)
        m_workspaceTitleLabel->setText(QString::fromUtf8("Admin panel"));
    if (m_workspaceSubtitleLabel)
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Spr\u00e1va u\u017eivatel\u016f, p\u0159ehled anal\u00fdz a logy serveru."));
    if (m_adminPanelView) m_adminPanelView->refresh();
}

void MainWindow::startImpersonation(const QString &token, const QString &userFullName,
                                    const QString &orgId, const QString &userId)
{
    (void)orgId;
    (void)userId;

    // Save current admin token so we can restore it later
    m_savedAdminToken = m_session.token();

    // Apply the impersonation token for all subsequent API calls
    m_session.setAccessToken(token);

    // Show the warning banner
    if (m_impersonationLabel) {
        m_impersonationLabel->setText(
            QString::fromUtf8("\u26a0\ufe0f Impersonace aktivn\u00ed \u2014 p\u0159ihl\u00e1\u0161en jako: %1")
                .arg(userFullName.isEmpty() ? userId : userFullName));
    }
    if (m_impersonationBanner) {
        m_impersonationBanner->setVisible(true);
    }

    // Reload the case list under the impersonated user's context
    if (m_caseListView) {
        m_caseListView->reloadCases(QString(), false);
    }
    showWelcomeView();
    statusBar()->showMessage(
        QString::fromUtf8("Impersonace: p\u0159ihl\u00e1\u0161en jako %1").arg(userFullName),
        6000);
}

void MainWindow::stopImpersonation()
{
    if (m_savedAdminToken.isEmpty()) return;

    // Restore admin token
    m_session.setAccessToken(m_savedAdminToken);
    m_savedAdminToken.clear();

    // Hide banner
    if (m_impersonationBanner) {
        m_impersonationBanner->setVisible(false);
    }

    // Reload case list under the original admin context
    if (m_caseListView) {
        m_caseListView->reloadCases(QString(), false);
    }
    showAdminPanelView();
    statusBar()->showMessage(QString::fromUtf8("Impersonace ukon\u010dena."), 4000);
}

void MainWindow::showCaseDetailView()
{
    if (m_caseColumn) m_caseColumn->show();
    if (m_detailStack) m_detailStack->setCurrentIndex(0);
    updateWorkspaceHeader();
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
        m_workspaceTitleLabel->setText(QString::fromUtf8("Zat\u00edm nen\u00ed aktivn\u00ed zak\u00e1zka"));
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Vyber zak\u00e1zku vlevo. V\u0161echny d\u016fle\u017eit\u00e9 kroky budeme dr\u017eet v jedn\u00e9 aktivn\u00ed kart\u011b."));
        return;
    }

    const QString sectionPrefix = m_caseListSection.isEmpty()
        ? QString::fromUtf8("Zak\u00e1zka")
        : m_caseListSection;
    m_workspaceTitleLabel->setText(sectionPrefix + QString::fromUtf8(" \u2013 ") + currentTitle);
    if (m_caseListView->currentCaseIsReferenceDataset()) {
        m_workspaceSubtitleLabel->setText(
            QString::fromUtf8("Toto je referen\u010dn\u00ed testovac\u00ed zak\u00e1zka z datasetu. Je vhodn\u00e1 pro ov\u011b\u0159en\u00ed anal\u00fdzy, n\u00e1vrhu a v\u00fdb\u011bru fotek."));
        return;
    }

    m_workspaceSubtitleLabel->setText(
        QString::fromUtf8("Toto je hlavn\u00ed pracovn\u00ed karta aktu\u00e1ln\u00ed zak\u00e1zky. Mo\u017enosti m\u00e1\u0161 vlevo, tady prob\u00edh\u00e1 samotn\u00e1 pr\u00e1ce na detailu."));
}

void MainWindow::setSidebarActiveSection(QPushButton *activeButton)
{
    const QString activeStyle =
        "background: #c97b3d; border-color: #c97b3d; color: #fff9f2;";
    const QList<QPushButton *> buttons = {
        m_sidebarServerCasesButton,
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

    QMessageBox msgBox(this);
    msgBox.setWindowTitle(QString::fromUtf8("Neulo\u017een\u00e9 zm\u011bny"));
    msgBox.setText(QString::fromUtf8("M\u00e1te neulo\u017een\u00e9 zm\u011bny v aktu\u00e1ln\u00ed zak\u00e1zce. Chcete odej\u00edt bez ulo\u017een\u00ed?"));
    msgBox.setIcon(QMessageBox::Question);
    auto *btnAno = msgBox.addButton(QString::fromUtf8("Ano, odej\u00edt"), QMessageBox::YesRole);
    msgBox.addButton(QString::fromUtf8("Ne, z\u016fstat"), QMessageBox::NoRole);
    msgBox.exec();
    return msgBox.clickedButton() == btnAno;
}

void MainWindow::openServerSetupDialog(bool firstTime)
{
    QSettings settings("NOVU", "NovuBuilder");
    const QString currentUrl = settings.value("server/url").toString();

    ServerSetupDialog dlg(currentUrl, this);
    if (firstTime) {
        dlg.setWindowTitle(QString::fromUtf8("Prvn\u00ed spou\u0161t\u011bn\u00ed \u2014 Nastaven\u00ed serveru"));
    }

    if (dlg.exec() == QDialog::Accepted) {
        const QString newUrl = dlg.serverUrl();
        if (!newUrl.isEmpty()) {
            settings.setValue("server/url", newUrl);
            ApiService::setGlobalBaseUrl(newUrl);
            m_session.refreshRealtimeConnection();
            statusBar()->showMessage(
                QString::fromUtf8("Server nastaven na: %1").arg(newUrl), 5000);
        }
    } else if (firstTime) {
        // User cancelled on first launch — use default
        ApiService::setGlobalBaseUrl(QString());
        m_session.refreshRealtimeConnection();
        statusBar()->showMessage(
            QString::fromUtf8("Server neni nastaven. Prihlaseni zustane blokovane, dokud nezadate URL serveru."),
            6000);
    }
}
