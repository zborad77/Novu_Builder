#include "loginview.h"

#include <QFrame>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QVBoxLayout>

LoginView::LoginView(QWidget *parent)
    : QWidget(parent)
{
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(28, 24, 28, 24);
    layout->setSpacing(0);

    auto *card = new QFrame(this);
    auto *cardLayout = new QVBoxLayout(card);
    cardLayout->setContentsMargins(24, 22, 24, 22);
    cardLayout->setSpacing(14);

    auto *eyebrow = new QLabel("FOTONABIDKA / LOGIN", card);
    eyebrow->setObjectName("eyebrowLabel");
    auto *title = new QLabel("Prihlaseni do desktop klienta", card);
    title->setObjectName("titleLabel");
    auto *subtitle = new QLabel(QString::fromUtf8("Zadej sv\u00e9 p\u0159ihla\u0161ovac\u00ed \u00fadaje pro p\u0159ipojen\u00ed k syst\u00e9mu NOVU."), card);
    subtitle->setWordWrap(true);
    subtitle->setObjectName("subtitleLabel");

    m_errorLabel = new QLabel(card);
    m_errorLabel->setObjectName("errorLabel");
    m_errorLabel->setWordWrap(true);
    m_errorLabel->hide();

    m_emailEdit = new QLineEdit(card);
    m_emailEdit->setPlaceholderText("E-mail");
    m_passwordEdit = new QLineEdit(card);
    m_passwordEdit->setPlaceholderText("Heslo");
    m_passwordEdit->setEchoMode(QLineEdit::Password);
    m_loginButton = new QPushButton("Prihlasit", card);
    m_loginButton->setWhatsThis(QString::fromUtf8("Ode\u0161le p\u0159ihla\u0161ovac\u00ed \u00fadaje na server. Po \u00fasp\u011b\u0161n\u00e9m p\u0159ihl\u00e1\u0161en\u00ed se otev\u0159e hlavn\u00ed obrazovka."));

    cardLayout->addWidget(eyebrow);
    cardLayout->addWidget(title);
    cardLayout->addWidget(subtitle);
    cardLayout->addWidget(m_errorLabel);
    cardLayout->addWidget(m_emailEdit);
    cardLayout->addWidget(m_passwordEdit);
    cardLayout->addWidget(m_loginButton, 0, Qt::AlignLeft);

    layout->addStretch();
    layout->addWidget(card, 0, Qt::AlignCenter);
    layout->addStretch();

    m_loginButton->setDefault(true);

    auto doLogin = [this]() {
        emit loginRequested(m_emailEdit->text(), m_passwordEdit->text());
    };
    connect(m_loginButton, &QPushButton::clicked, this, doLogin);
    connect(m_emailEdit, &QLineEdit::returnPressed, this, doLogin);
    connect(m_passwordEdit, &QLineEdit::returnPressed, this, doLogin);

    setStyleSheet(R"(
        QWidget {
            background: #f4f1ea;
            color: #243042;
            font-size: 14px;
        }
        QFrame {
            background: #fffaf2;
            border: 1px solid #eadcc8;
            border-radius: 18px;
            min-width: 440px;
        }
        QLabel#eyebrowLabel {
            color: #b46d35;
            font-weight: 700;
            letter-spacing: 1px;
            font-size: 12px;
        }
        QLabel#titleLabel {
            font-size: 28px;
            font-weight: 700;
            color: #1f2933;
        }
        QLabel#subtitleLabel {
            color: #607080;
        }
        QLineEdit {
            min-width: 240px;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #eadcc8;
            background: #fffdf8;
        }
        QPushButton {
            background: #c97b3d;
            color: white;
            border: none;
            border-radius: 12px;
            padding: 12px 24px;
            font-weight: 700;
        }
        QPushButton:disabled {
            background: #d4a57a;
        }
        QLabel#errorLabel {
            background: #fdecea;
            color: #c0392b;
            border: 1px solid #f5c6c2;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 13px;
        }
    )");
}

void LoginView::showError(const QString &message)
{
    if (m_errorLabel) {
        m_errorLabel->setText(message);
        m_errorLabel->show();
    }
}

void LoginView::clearError()
{
    if (m_errorLabel) {
        m_errorLabel->hide();
        m_errorLabel->clear();
    }
}

void LoginView::setLoading(bool loading)
{
    if (m_loginButton) {
        m_loginButton->setEnabled(!loading);
        m_loginButton->setText(loading ? "Prihlasuji..." : "Prihlasit");
    }
    if (m_emailEdit) {
        m_emailEdit->setEnabled(!loading);
    }
    if (m_passwordEdit) {
        m_passwordEdit->setEnabled(!loading);
    }
}
