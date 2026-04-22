#include "loginviewmodel.h"

LoginViewModel::LoginViewModel(QObject *parent)
    : QObject(parent)
{
}

LoginDto LoginViewModel::initialState() const
{
    return {
        .email = "demo@novu.local",
        .password = "demo1234"
    };
}

bool LoginViewModel::canLogin(const LoginDto &state) const
{
    return !state.email.trimmed().isEmpty() && !state.password.isEmpty();
}
