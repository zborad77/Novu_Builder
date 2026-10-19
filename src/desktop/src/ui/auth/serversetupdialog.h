#pragma once

#include <QDialog>

class QLabel;
class QLineEdit;
class QPushButton;

class ServerSetupDialog : public QDialog
{
    Q_OBJECT

public:
    explicit ServerSetupDialog(const QString &currentUrl = {}, QWidget *parent = nullptr);

    [[nodiscard]] QString serverUrl() const;

private:
    void testConnection();
    void updateSaveState();

    QLineEdit *m_urlEdit = nullptr;
    QPushButton *m_testButton = nullptr;
    QPushButton *m_saveButton = nullptr;
    QLabel *m_statusLabel = nullptr;
};
