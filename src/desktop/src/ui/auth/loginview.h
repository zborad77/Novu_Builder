#pragma once

#include <QWidget>

class QLabel;
class QLineEdit;
class QPushButton;

class LoginView : public QWidget
{
    Q_OBJECT

public:
    explicit LoginView(QWidget *parent = nullptr);

    void showError(const QString &message);
    void clearError();
    void setLoading(bool loading);

    void setServerUrl(const QString &url);

signals:
    void loginRequested(const QString &email, const QString &password);
    void changeServerRequested();

private:
    QLineEdit *m_emailEdit = nullptr;
    QLineEdit *m_passwordEdit = nullptr;
    QPushButton *m_loginButton = nullptr;
    QLabel *m_errorLabel = nullptr;
    QLabel *m_serverUrlLabel = nullptr;
};
