#include "dashboardviewmodel.h"

DashboardViewModel::DashboardViewModel(QObject *parent)
    : QObject(parent)
{
}

const char *DashboardViewModel::title() const
{
    return "Dashboard";
}
