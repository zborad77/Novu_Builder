#pragma once

#include <QWidget>

class QLabel;
class QListWidget;

class DashboardView : public QWidget
{
    Q_OBJECT

public:
    explicit DashboardView(QWidget *parent = nullptr);

    void loadStats();

signals:
    void newCaseRequested();
    void loadCasesRequested();

protected:
    void showEvent(QShowEvent *) override;

private:
    QLabel *m_statTotal     = nullptr;
    QLabel *m_statAnalyzing = nullptr;
    QLabel *m_statReady     = nullptr;
    QLabel *m_statSent      = nullptr;
    QListWidget *m_recentList = nullptr;
    QLabel *m_statusLabel   = nullptr;
};
