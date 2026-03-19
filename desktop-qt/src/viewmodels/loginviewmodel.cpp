#include "loginviewmodel.h"

LoginDto LoginViewModel::initialState() const
{
    return {
        .email = "radek@novu.local",
        .password = "demo"
    };
}

bool LoginViewModel::canLogin(const LoginDto &state) const
{
    return !state.email.trimmed().isEmpty() && !state.password.isEmpty();
}
