#include "serversetupdialog.h"

#include <QDialogButtonBox>
#include <QFrame>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QEventLoop>
#include <QStyle>
#include <QTimer>
#include <QJsonDocument>
#include <QJsonObject>

ServerSetupDialog::ServerSetupDialog(const QString &currentUrl, QWidget *parent)
    : QDialog(parent)
{
    setWindowTitle(QString::fromUtf8("Nastaven\u00ed serveru \u2014 FotoNab\u00eddka Desktop"));
    setMinimumWidth(480);

    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(24, 20, 24, 20);
    layout->setSpacing(16);

    auto *eyebrow = new QLabel(QString::fromUtf8("KONFIGURACE SERVERU"), this);
    eyebrow->setObjectName("eyebrowLabel");

    auto *title = new QLabel(QString::fromUtf8("Adresa va\u0161eho NOVU serveru"), this);
    title->setObjectName("titleLabel");

    auto *subtitle = new QLabel(
        QString::fromUtf8(
            "Ka\u017ed\u00e1 firma m\u00e1 vlastn\u00ed server. Zadejte adresu, kterou V\u00e1m "
            "p\u0159id\u011blil spr\u00e1vce syst\u00e9mu NOVU."),
        this);
    subtitle->setWordWrap(true);
    subtitle->setObjectName("subtitleLabel");

    auto *urlLabel = new QLabel(QString::fromUtf8("URL serveru"), this);

    m_urlEdit = new QLineEdit(this);
    m_urlEdit->setPlaceholderText("https://vas-server.novu.cz/api/v1");
    if (!currentUrl.isEmpty()) {
        m_urlEdit->setText(currentUrl);
    }

    auto *exampleLabel = new QLabel(
        QString::fromUtf8("P\u0159\u00edklady: <i>https://firma-abc.novu.cz/api/v1</i> &nbsp;nebo&nbsp; <i>http://192.168.1.10:8000/api/v1</i>"),
        this);
    exampleLabel->setObjectName("exampleLabel");

    m_statusLabel = new QLabel(this);
    m_statusLabel->setObjectName("statusLabel");
    m_statusLabel->setWordWrap(true);
    m_statusLabel->hide();

    auto *buttonRow = new QHBoxLayout();
    m_testButton = new QPushButton(QString::fromUtf8("Otestovat p\u0159ipojen\u00ed"), this);
    m_testButton->setObjectName("testButton");

    m_saveButton = new QPushButton(QString::fromUtf8("Ulo\u017eit a pokra\u010dovat"), this);
    m_saveButton->setObjectName("saveButton");
    m_saveButton->setEnabled(!currentUrl.isEmpty());

    buttonRow->addWidget(m_testButton);
    buttonRow->addStretch();
    buttonRow->addWidget(m_saveButton);

    layout->addWidget(eyebrow);
    layout->addWidget(title);
    layout->addWidget(subtitle);
    layout->addSpacing(4);
    layout->addWidget(urlLabel);
    layout->addWidget(m_urlEdit);
    layout->addWidget(exampleLabel);
    layout->addWidget(m_statusLabel);
    layout->addLayout(buttonRow);

    connect(m_urlEdit, &QLineEdit::textChanged, this, &ServerSetupDialog::updateSaveState);
    connect(m_testButton, &QPushButton::clicked, this, &ServerSetupDialog::testConnection);
    connect(m_saveButton, &QPushButton::clicked, this, &QDialog::accept);

    setStyleSheet(R"(
        QDialog {
            background: #f4f1ea;
        }
        QLabel {
            color: #243042;
            font-size: 14px;
        }
        QLabel#eyebrowLabel {
            color: #b46d35;
            font-weight: 700;
            letter-spacing: 1px;
            font-size: 12px;
        }
        QLabel#titleLabel {
            font-size: 22px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#subtitleLabel {
            color: #607080;
            font-size: 13px;
        }
        QLabel#exampleLabel {
            color: #8a9aaa;
            font-size: 12px;
        }
        QLabel#statusLabel[ok="true"] {
            background: #eaf6ec;
            color: #1e7e34;
            border: 1px solid #b2dfbb;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLabel#statusLabel[ok="false"] {
            background: #fdecea;
            color: #c0392b;
            border: 1px solid #f5c6c2;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 13px;
        }
        QLineEdit {
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #eadcc8;
            background: #fffdf8;
            font-size: 14px;
        }
        QPushButton#testButton {
            background: #f0e8da;
            border: 1px solid #d9c9b0;
            border-radius: 10px;
            padding: 10px 20px;
            color: #6b4f2e;
            font-weight: 600;
        }
        QPushButton#testButton:hover {
            background: #e8d9c4;
        }
        QPushButton#saveButton {
            background: #c97b3d;
            color: white;
            border: none;
            border-radius: 10px;
            padding: 10px 24px;
            font-weight: 700;
        }
        QPushButton#saveButton:disabled {
            background: #d4a57a;
        }
    )");
}

QString ServerSetupDialog::serverUrl() const
{
    return m_urlEdit ? m_urlEdit->text().trimmed() : QString{};
}

void ServerSetupDialog::updateSaveState()
{
    if (m_saveButton) {
        m_saveButton->setEnabled(!m_urlEdit->text().trimmed().isEmpty());
    }
}

void ServerSetupDialog::testConnection()
{
    const QString url = m_urlEdit ? m_urlEdit->text().trimmed() : QString{};
    if (url.isEmpty()) {
        return;
    }

    m_testButton->setEnabled(false);
    m_testButton->setText(QString::fromUtf8("Testuje se\u2026"));
    if (m_statusLabel) {
        m_statusLabel->hide();
    }

    // Test: GET /health endpoint
    QString healthUrl = url;
    // Strip trailing /api/v1 variants and append /health
    if (healthUrl.endsWith("/api/v1")) {
        healthUrl = healthUrl.left(healthUrl.length() - 7);
    } else if (healthUrl.endsWith("/api/v1/")) {
        healthUrl = healthUrl.left(healthUrl.length() - 8);
    }
    healthUrl += "/api/v1/health";

    QNetworkAccessManager manager;
    QNetworkRequest request{QUrl{healthUrl}};
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    auto *reply = manager.get(request);

    QEventLoop loop;
    QTimer timer;
    timer.setSingleShot(true);
    QObject::connect(reply, &QNetworkReply::finished, &loop, &QEventLoop::quit);
    QObject::connect(&timer, &QTimer::timeout, &loop, [&]() {
        if (reply->isRunning()) reply->abort();
        loop.quit();
    });
    timer.start(6000);
    loop.exec();

    const bool ok = reply->error() == QNetworkReply::NoError;
    reply->deleteLater();

    m_testButton->setEnabled(true);
    m_testButton->setText(QString::fromUtf8("Otestovat p\u0159ipojen\u00ed"));

    if (m_statusLabel) {
        if (ok) {
            m_statusLabel->setText(QString::fromUtf8("\u2705 Server je dostupn\u00fd a odpov\u00edd\u00e1."));
            m_statusLabel->setProperty("ok", true);
            if (m_saveButton) m_saveButton->setEnabled(true);
        } else {
            m_statusLabel->setText(QString::fromUtf8(
                "\u274c Server neodpov\u00edd\u00e1. Zkontrolujte adresu a zda je server spu\u0161t\u011bn."));
            m_statusLabel->setProperty("ok", false);
        }
        m_statusLabel->show();
        m_statusLabel->style()->unpolish(m_statusLabel);
        m_statusLabel->style()->polish(m_statusLabel);
    }
}
