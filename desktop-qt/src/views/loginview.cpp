#include "loginview.h"

#include <QFormLayout>
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
    auto *subtitle = new QLabel(
        "Zatim jde o lokalni prototyp bez backend auth. Tlacitko jen prepne aplikaci do pracovniho shellu.",
        card);
    subtitle->setWordWrap(true);
    subtitle->setObjectName("subtitleLabel");

    auto *formLayout = new QFormLayout();
    formLayout->setLabelAlignment(Qt::AlignLeft);
    formLayout->setFormAlignment(Qt::AlignLeft | Qt::AlignTop);
    formLayout->setHorizontalSpacing(16);
    formLayout->setVerticalSpacing(12);

    m_emailEdit = new QLineEdit(card);
    m_emailEdit->setPlaceholderText("radek@novu.local");
    m_passwordEdit = new QLineEdit(card);
    m_passwordEdit->setPlaceholderText("demo");
    m_passwordEdit->setEchoMode(QLineEdit::Password);
    m_loginButton = new QPushButton("Prihlasit", card);

    formLayout->addRow("E-mail", m_emailEdit);
    formLayout->addRow("Heslo", m_passwordEdit);

    cardLayout->addWidget(eyebrow);
    cardLayout->addWidget(title);
    cardLayout->addWidget(subtitle);
    cardLayout->addLayout(formLayout);
    cardLayout->addWidget(m_loginButton, 0, Qt::AlignLeft);

    layout->addStretch();
    layout->addWidget(card, 0, Qt::AlignCenter);
    layout->addStretch();

    connect(m_loginButton, &QPushButton::clicked, this, [this]() {
        emit loginRequested(m_emailEdit->text(), m_passwordEdit->text());
    });

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
    )");
}
