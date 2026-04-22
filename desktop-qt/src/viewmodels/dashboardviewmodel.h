#pragma once

#include <QObject>

class DashboardViewModel : public QObject
{
    Q_OBJECT
public:
    explicit DashboardViewModel(QObject *parent = nullptr);

    [[nodiscard]] const char *title() const;
};
